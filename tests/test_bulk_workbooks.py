import asyncio
import hashlib
import importlib.util
import io
import json
import runpy
import sys
import tempfile
import types
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'bulk_test_studio'
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / 'server_extensions/assistant_studio')]
sys.modules[PACKAGE] = package
copy = __import__(PACKAGE + '.workbook_copy', fromlist=['copy_column'])


def serialize(book):
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def source(rows):
    book = Workbook()
    book.active.title = 'SOW'
    for row in rows:
        book.active.append(row)
    return book


def destination():
    book = Workbook()
    book.active.title = 'Template'
    book.active.append(['Description', 'LID', 'Qty'])
    book.active['A2'] = 'Keep template text'
    book.active['C2'] = '=SUM(1,2)'
    book.create_sheet('Untouched')['A1'] = 'Preserve original worksheet'
    return book


class BulkCopyTests(unittest.TestCase):
    def apply(self, src, dest=None, **kwargs):
        return copy.copy_column(src if isinstance(src, bytes) else serialize(src),
                                serialize(dest or destination()), source_sheet='SOW', source_header='Tool ID',
                                destination_sheet='Template', destination_header='LID', **kwargs)

    def test_large_source_copy_exceeds_old_limit_and_preserves_every_identifier(self):
        book = Workbook(write_only=True)
        sheet = book.create_sheet('SOW')
        sheet.append(['Tool ID', 'B', 'C', 'D', 'E', 'F'])
        for number in range(12000):
            sheet.append([f'{number:08d}', 'description', number, 'unit', 'active', 'schedule'])
        data = serialize(book)  # 72006 populated source cells; old reader rejected it
        before = hashlib.sha256(data).hexdigest()
        output, summary = self.apply(data)
        result = load_workbook(io.BytesIO(output))
        self.assertEqual(summary['rows_copied'], 12000)
        self.assertEqual(summary['nonempty_values'], 12000)
        self.assertEqual([result['Template'].cell(row+2, 2).value for row in range(12000)],
                         [f'{number:08d}' for number in range(12000)])
        self.assertEqual(result['Template']['C2'].value, '=SUM(1,2)')
        self.assertEqual(result['Template']['A2'].value, 'Keep template text')
        self.assertEqual(result['Untouched']['A1'].value, 'Preserve original worksheet')
        self.assertEqual(hashlib.sha256(data).hexdigest(), before)

    def test_blanks_zero_padding_and_literal_formula_text(self):
        src = source([['Tool ID'], ['000012'], [None], [12], ['=literal']])
        src.active['A4'].number_format = '000000'
        src.active['A5'].data_type = 's'
        output, summary = self.apply(src)
        sheet = load_workbook(io.BytesIO(output))['Template']
        self.assertEqual([sheet.cell(r,2).value for r in range(2,6)], ['000012', None, 12, '=literal'])
        self.assertEqual(sheet['B4'].number_format, '000000')
        self.assertEqual(sheet['B5'].data_type, 's')
        self.assertEqual(summary['rows_copied'], 4)
        self.assertEqual(summary['nonempty_values'], 3)

    def test_conflicting_values_and_merged_cells_require_resolution(self):
        src = source([['Tool ID'], ['0001']])
        dest = destination()
        dest.active['B2'] = 'different ID'
        with self.assertRaisesRegex(ValueError, 'Confirm replacement'):
            self.apply(src, dest)
        output, _ = self.apply(src, dest, overwrite=True)
        self.assertEqual(load_workbook(io.BytesIO(output)).active['B2'].value, '0001')
        dest.active.merge_cells('B2:C2')
        with self.assertRaisesRegex(ValueError, 'merged cells'):
            self.apply(src, dest, overwrite=True)

    def test_formula_requires_cached_value_instead_of_guessing(self):
        src = source([['Tool ID'], ['=SUM(1,2)']])
        with self.assertRaisesRegex(ValueError, 'no saved value'):
            self.apply(src)
        raw = serialize(src)
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as z, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as out:
            for name in z.namelist():
                data = z.read(name)
                if name == 'xl/worksheets/sheet1.xml':
                    data = data.replace(b'<v></v>', b'<v>3</v>')
                out.writestr(name, data)
        result, _ = self.apply(output.getvalue())
        self.assertEqual(load_workbook(io.BytesIO(result)).active['B2'].value, 3)

    def test_header_selection_is_unique_and_paths_are_only_labels(self):
        src = source([['Tool ID', 'Tool ID'], ['001', '002']])
        with self.assertRaisesRegex(ValueError, 'matched 2'):
            self.apply(src)
        src = source([['Tool ID'], ['old'], ['Tool ID'], ['new']])
        with self.assertRaises(ValueError):
            self.apply(src)
        output, summary = self.apply(src, source_header_row=3)
        self.assertEqual(load_workbook(io.BytesIO(output)).active['B2'].value, 'new')
        self.assertEqual(summary['rows_copied'], 1)
        self.assertEqual(copy.filename(r'C:\Users\Rod\OneDrive\Schedule.xlsx'), 'Schedule.xlsx')
        self.assertEqual(copy.filename('/server/folder/Schedule.xlsx'), 'Schedule.xlsx')
        with self.assertRaises(ValueError):
            copy.filename('https://example.com/Schedule.xlsx')

    def test_archive_safety_survives_larger_limits_and_destination_parts_preserved(self):
        src = serialize(source([['Tool ID'], ['001']]))
        bad = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(src)) as z, zipfile.ZipFile(bad, 'w') as out:
            for name in z.namelist():
                out.writestr(name, z.read(name))
            out.writestr('xl/externalLinks/evil.xml', '<x/>')
        with self.assertRaisesRegex(ValueError, 'external data'):
            self.apply(bad.getvalue())
        original = serialize(destination())
        edited, _ = copy.copy_column(src, original, source_sheet='SOW', source_header='Tool ID',
                                    destination_sheet='Template', destination_header='LID')
        with zipfile.ZipFile(io.BytesIO(original)) as a, zipfile.ZipFile(io.BytesIO(edited)) as b:
            self.assertEqual(a.read('xl/worksheets/sheet2.xml'), b.read('xl/worksheets/sheet2.xml'))

    def test_installer_freezes_current_source_and_preserves_other_hooks(self):
        module = runpy.run_path(str(ROOT / 'deploy/updaters/install_bulk_workbooks.py'))
        for name, text in module['payload']().items():
            self.assertEqual(text, (ROOT / 'server_extensions/assistant_studio' / name).read_text())
        old = 'def install(app):\n    _install_spreadsheet_tools()\n    _install_rog_worker(app)\n'
        new = module['patch_bootstrap'](old)
        self.assertIn('_install_rog_worker(app)', new)
        self.assertEqual(module['patch_bootstrap'](new), new)


@unittest.skipUnless(importlib.util.find_spec('sqlalchemy') and importlib.util.find_spec('aiosqlite'), 'SQL test dependencies')
class OwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from sqlalchemy import Boolean, Column, Integer, JSON, String, Uuid
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.orm import DeclarativeBase

        class Base(DeclarativeBase):
            pass

        class Document(Base):
            __tablename__ = 'copy_documents'
            id = Column(Uuid(as_uuid=True), primary_key=True)
            user_id = Column(Uuid(as_uuid=True))
            title = Column(String)
            file_type = Column(String)
            storage_key = Column(String)
            project_id = Column(Uuid(as_uuid=True), nullable=True)

        class User(Base):
            __tablename__ = 'copy_users'
            id = Column(Uuid(as_uuid=True), primary_key=True)
            is_active = Column(Boolean)

        class Conversation(Base):
            __tablename__ = 'copy_conversations'
            id = Column(Uuid(as_uuid=True), primary_key=True)
            user_id = Column(Uuid(as_uuid=True))

        class Message(Base):
            __tablename__ = 'copy_messages'
            id = Column(Uuid(as_uuid=True), primary_key=True)
            conversation_id = Column(Uuid(as_uuid=True))
            position = Column(Integer)
            role = Column(String)
            attachments = Column(JSON)

        self.Document, self.User = Document, User
        self.Conversation, self.Message = Conversation, Message
        self.db_engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.addAsyncCleanup(self.db_engine.dispose)
        async with self.db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.maker = async_sessionmaker(self.db_engine, expire_on_commit=False)
        self.owner, self.other = uuid.uuid4(), uuid.uuid4()
        self.source_id, self.target_id, self.private_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with self.maker() as db:
            db.add_all([User(id=self.owner, is_active=True), User(id=self.other, is_active=True),
                        Document(id=self.source_id, user_id=self.owner, title='Schedule.xlsx', file_type='xlsx', storage_key='source'),
                        Document(id=self.target_id, user_id=self.owner, title='Template.xlsx', file_type='xlsx', storage_key='target'),
                        Document(id=self.private_id, user_id=self.other, title='Schedule.xlsx', file_type='xlsx', storage_key='private')])
            await db.commit()
        self.tools = __import__(PACKAGE + '.workbook_copy_tools', fromlist=['resolve'])

    async def test_path_only_matches_own_uploaded_filename_and_never_private_documents(self):
        async with self.maker() as db:
            doc = await self.tools.resolve(db, self.Document, self.owner, None, r'C:\Users\Rod\OneDrive\Schedule.xlsx')
            self.assertEqual(doc.id, self.source_id)
            with self.assertRaisesRegex(ValueError, 'unavailable to this account'):
                await self.tools.resolve(db, self.Document, self.owner, str(self.private_id), None)
            with self.assertRaisesRegex(ValueError, 'Upload Missing.xlsx'):
                await self.tools.resolve(db, self.Document, self.owner, None, r'C:\Missing.xlsx')
            db.add(self.Document(id=uuid.uuid4(), user_id=self.owner, title='Schedule.xlsx', file_type='xlsx', storage_key='another'))
            await db.commit()
            with self.assertRaisesRegex(ValueError, 'Multiple uploaded copies'):
                await self.tools.resolve(db, self.Document, self.owner, None, 'Schedule.xlsx')

    async def test_duplicate_resolution_prefers_current_attachment_then_latest_chat_attachment(self):
        duplicate, conv, private_conv = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with self.maker() as db:
            db.add_all([
                self.Document(id=duplicate, user_id=self.owner, title='Schedule.xlsx', file_type='xlsx', storage_key='duplicate'),
                self.Conversation(id=conv, user_id=self.owner),
                self.Conversation(id=private_conv, user_id=self.other),
                self.Message(id=uuid.uuid4(), conversation_id=conv, position=1, role='user', attachments=[{'id': str(self.source_id)}]),
                self.Message(id=uuid.uuid4(), conversation_id=conv, position=3, role='user', attachments=[{'id': str(duplicate)}]),
            ])
            await db.commit()
            models = types.ModuleType('app.models')
            models.Conversation, models.Message = self.Conversation, self.Message
            with patch.dict(sys.modules, {'app.models': models}):
                ctx = types.SimpleNamespace(user_id=self.owner, conversation_id=conv, attachment_ids=[self.source_id])
                groups = await self.tools.context_groups(db, ctx)
                picked = await self.tools.resolve(db, self.Document, self.owner, None, 'Schedule.xlsx', groups)
                self.assertEqual(picked.id, self.source_id)
                ctx.attachment_ids = []
                groups = await self.tools.context_groups(db, ctx)
                picked = await self.tools.resolve(db, self.Document, self.owner, None, 'Schedule.xlsx', groups)
                self.assertEqual(picked.id, duplicate)
                ctx.conversation_id = private_conv
                self.assertEqual(await self.tools.context_groups(db, ctx), [[]])
            with self.assertRaisesRegex(ValueError, 'Attach just the intended workbook'):
                await self.tools.resolve(db, self.Document, self.owner, None, 'Schedule.xlsx', [[self.source_id, duplicate]])
            selected = await self.tools.resolve(db, self.Document, self.owner, None, 'Schedule.xlsx',
                                                [[self.private_id, 'not-a-uuid'], [self.source_id]])
            self.assertEqual(selected.id, self.source_id)

    async def test_chat_tool_saves_actual_download_and_rejects_other_account_before_reading(self):
        reads, saved = [], []
        data = {'source': serialize(source([['Tool ID'], ['00012'], ['00013']])), 'target': serialize(destination())}

        async def get(key):
            reads.append(key)
            return data[key]

        async def upload(db, settings, files, unused, **kwargs):
            key = str(uuid.uuid4())
            saved.append(kwargs['data'])
            row = self.Document(id=uuid.uuid4(), user_id=kwargs['user_id'], title=kwargs['filename'], file_type='xlsx',
                                storage_key=key, project_id=kwargs['project_id'])
            data[key] = kwargs['data']
            db.add(row)
            await db.flush()
            return row

        class InputError(ValueError):
            pass

        assistant = types.ModuleType('app.services.assistant_tools')
        assistant.TOOLS = {}
        assistant.ToolInputError = InputError
        assistant.Tool = lambda spec, label, run: types.SimpleNamespace(spec=spec, label=label, run=run)
        assistant.ToolOutcome = lambda data, summary, action=None: types.SimpleNamespace(data=data, summary=summary, action=action)
        models, services, files = types.ModuleType('app.models'), types.ModuleType('app.services'), types.ModuleType('app.services.files_service')
        models.User, models.KnowledgeDocument = self.User, self.Document
        services.assistant_tools = assistant
        files.store_upload = upload
        files.build_files_runtime = lambda settings: None
        ai = types.ModuleType('dhanz_ai')
        ai.ToolSpec = lambda **kwargs: types.SimpleNamespace(**kwargs)
        modules = {'app.services': services, 'app.services.assistant_tools': assistant, 'app.models': models,
                   'app.services.files_service': files, 'dhanz_ai': ai}
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, modules):
            self.tools.install()
            run = assistant.TOOLS['copy_workbook_column'].run
            ctx = types.SimpleNamespace(user_id=self.owner, maker=self.maker,
                                        settings=types.SimpleNamespace(storage_dir=folder),
                                        files=types.SimpleNamespace(storage=types.SimpleNamespace(get=get)),
                                        attachment_ids=[self.source_id])
            args = {'source_document_id': str(self.private_id), 'destination_document_id': str(self.target_id),
                    'source_sheet': 'SOW', 'source_header': 'Tool ID', 'destination_sheet': 'Template', 'destination_header': 'LID'}
            with self.assertRaises(InputError):
                await run(ctx, args)
            self.assertEqual(reads, [])
            async with self.maker() as db:
                db.add(self.Document(id=uuid.uuid4(), user_id=self.owner, title='Schedule.xlsx', file_type='xlsx', storage_key='old-copy'))
                await db.commit()
            args.pop('source_document_id')
            args['source_path'] = r'C:\OneDrive\Schedule.xlsx'
            result = await run(ctx, args)
            self.assertTrue(result.data['created'])
            self.assertEqual(result.data['rows_copied'], 2)
            self.assertEqual(result.action['type'], 'download_file')
            self.assertEqual(load_workbook(io.BytesIO(saved[0])).active['B2'].value, '00012')
            self.assertIs(await run(ctx, args), result)
            self.assertEqual(len(saved), 1)


if __name__ == '__main__':
    unittest.main()
