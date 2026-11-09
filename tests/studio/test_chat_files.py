import json
import runpy
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.assistant_studio import chat_files
from app.db.base import Base
from app.models import Conversation, KnowledgeDocument, Message, Project, User


@pytest_asyncio.fixture
async def setup_files():
    sql = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with sql.begin() as db:
        await db.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(sql, expire_on_commit=False)
    owner, other = uuid.uuid4(), uuid.uuid4()
    project, unrelated, alien_project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chat, sibling, elsewhere, alien_chat, temporary = [uuid.uuid4() for _ in range(5)]
    docs = {name: uuid.uuid4() for name in ('source', 'generated', 'project', 'sibling', 'unrelated', 'alien', 'deleted', 'old', 'temporary')}
    async with maker() as db:
        db.add_all([User(id=owner, email='file-owner@example.test', display_name='Owner'),
                    User(id=other, email='file-other@example.test', display_name='Other')])
        await db.flush()
        db.add_all([Project(id=project, user_id=owner, name='Budget topic'),
                    Project(id=unrelated, user_id=owner, name='Unrelated topic'),
                    Project(id=alien_project, user_id=other, name='Other account topic')])
        await db.flush()
        for cid, uid, pid, temp in ((chat, owner, project, False), (sibling, owner, project, False),
                                    (elsewhere, owner, unrelated, False), (alien_chat, other, alien_project, False),
                                    (temporary, owner, project, True)):
            db.add(Conversation(id=cid, user_id=uid, project_id=pid, title='Test chat', temporary=temp))
        await db.flush()
        for name, identifier in docs.items():
            uid = other if name == 'alien' else owner
            pid = project if name == 'project' else unrelated if name == 'unrelated' else None
            db.add(KnowledgeDocument(id=identifier, user_id=uid, project_id=pid, kind='file',
                                     url='upload:'+str(identifier), title=name+'.xlsx', file_type='xlsx',
                                     storage_key=None if name == 'deleted' else identifier.hex,
                                     content='PRIVATE FILE BODY '+name, content_hash='a'*64))
        await db.flush()

        def msg(cid, position, *, names=(), generated=(), role='user'):
            return Message(id=uuid.uuid4(), conversation_id=cid, position=position, role=role,
                           content='ordinary chat text', status='complete',
                           attachments=[{'id': str(docs[n]), 'filename': n+'.xlsx'} for n in names] or None,
                           tool_activity=[{'tool': 'excel_workbook', 'action': {'type': 'download_file', 'id': str(docs[n]), 'filename': n+'.xlsx'}} for n in generated] or None)
        db.add_all([msg(chat, 0, names=('old',)), msg(chat, 1, names=('source', 'deleted', 'alien')),
                    msg(chat, 2, generated=('generated',), role='assistant'),
                    msg(sibling, 0, names=('sibling',)), msg(elsewhere, 0, names=('unrelated',)),
                    msg(alien_chat, 0, names=('alien',)), msg(temporary, 0, names=('temporary',))])
        db.add_all([msg(chat, i) for i in range(3, 303)])
        await db.commit()
    yield SimpleNamespace(maker=maker, owner=owner, other=other, project=project, chat=chat,
                          sibling=sibling, alien_chat=alien_chat, temporary=temporary, docs=docs)
    await sql.dispose()


@pytest.mark.asyncio
async def test_catalog_survives_long_history_and_contains_uploaded_and_generated_names(setup_files):
    s = setup_files
    async with s.maker() as db:
        result = await chat_files.catalog(db, s.owner, s.chat, scope_name='chat')
    assert {f['filename'] for f in result['files']} == {'old.xlsx', 'source.xlsx', 'generated.xlsx'}
    assert all(f['scope'] == 'this_chat' for f in result['files'])
    assert 'PRIVATE FILE BODY' not in json.dumps(result)
    assert 'storage_key' not in json.dumps(result)


@pytest.mark.asyncio
async def test_topic_catalog_includes_owned_project_and_sibling_chat_but_not_unrelated_or_temporary(setup_files):
    s = setup_files
    async with s.maker() as db:
        result = await chat_files.catalog(db, s.owner, s.chat)
    assert {f['filename'] for f in result['files']} == {'old.xlsx', 'source.xlsx', 'generated.xlsx', 'project.xlsx', 'sibling.xlsx'}


@pytest.mark.asyncio
async def test_ownership_deletion_and_temporary_chat_rules(setup_files):
    s = setup_files
    async with s.maker() as db:
        assert not (await chat_files.catalog(db, s.owner, s.alien_chat))['files']
        temp = await chat_files.catalog(db, s.owner, s.temporary)
        assert {f['filename'] for f in temp['files']} == {'temporary.xlsx'}
        source = await db.get(KnowledgeDocument, s.docs['source'])
        await db.delete(source)
        await db.commit()
        assert 'source.xlsx' not in {f['filename'] for f in (await chat_files.catalog(db, s.owner, s.chat))['files']}


@pytest.mark.asyncio
async def test_name_search_pagination_and_read_scope(setup_files):
    s = setup_files
    async with s.maker() as db:
        found = await chat_files.catalog(db, s.owner, s.chat, filename='OLD.XLSX')
        assert [f['filename'] for f in found['files']] == ['old.xlsx']
        first = await chat_files.catalog(db, s.owner, s.chat, limit=1)
        second = await chat_files.catalog(db, s.owner, s.chat, limit=1, offset=1)
        assert first['has_more'] and first['files'][0]['document_id'] != second['files'][0]['document_id']
        doc = await chat_files.retained_document(db, s.owner, s.chat, s.docs['sibling'])
        assert doc.id == s.docs['sibling']
        for key in ('unrelated', 'alien', 'deleted', 'temporary'):
            with pytest.raises(ValueError):
                await chat_files.retained_document(db, s.owner, s.chat, s.docs[key])


@pytest.mark.asyncio
async def test_turn_hook_preserves_existing_instructions_and_reads_retained_file_without_upload(setup_files):
    from app.services import assistant_tools, chat_service
    s = setup_files

    async def original(db, user, conv):
        return {'project_id': conv.project_id, 'project_instructions': 'Keep existing project guidance.', 'memories': ['User preference']}

    with patch.object(chat_service, '_turn_context', original), patch.dict(assistant_tools.TOOLS):
        chat_files.install(SimpleNamespace())
        async with s.maker() as db:
            conv = await db.get(Conversation, s.chat)
            user = await db.get(User, s.owner)
            result = await chat_service._turn_context(db, user, conv)
        assert 'Keep existing project guidance.' in result['project_instructions']
        assert 'old.xlsx' in result['project_instructions']
        assert result['memories'] == ['User preference']
        assert 'PRIVATE FILE BODY' not in result['project_instructions']
        ctx = SimpleNamespace(maker=s.maker, user_id=s.owner, conversation_id=s.chat)
        outcome = await assistant_tools.TOOLS['chat_files'].run(ctx, {'operation': 'read', 'document_id': str(s.docs['old']), 'max_chars': 7})
        assert outcome.data['untrusted_file_text'] == 'PRIVATE'
        assert outcome.data['next_char'] == 7


def test_frozen_installer_preserves_other_startup_hooks():
    root = Path(__file__).resolve().parents[2]
    module = runpy.run_path(str(root / 'deploy/updaters/install_chat_files.py'))
    assert module['payload']()['module'] == (root / 'server_extensions/assistant_studio/chat_files.py').read_text()
    source = 'def install(app):\n    _install_bulk_workbooks()\n    _install_rog_worker(app)\n'
    updated = module['patch_bootstrap'](source)
    assert '_install_rog_worker(app)' in updated
    assert module['patch_bootstrap'](updated) == updated
    staged = module['image_sources'](source)
    assert set(staged) == set(module['MODULES'])
    assert staged['bootstrap.py'] == updated
    assert staged['chat_files.py'] == module['payload']()['module']
