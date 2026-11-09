"""Resolve owned uploads and copy entire columns without sending rows to an LLM."""
import asyncio
import contextlib
import fcntl
import functools
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from . import workbook_copy as engine


async def context_groups(db, ctx):
    """Prefer explicit turn attachments, then the latest attachments in this chat."""
    groups = [getattr(ctx, 'attachment_ids', None) or []]
    conversation_id = getattr(ctx, 'conversation_id', None)
    if not conversation_id:
        return groups
    from app.models import Conversation, Message

    conversation = await db.get(Conversation, uuid.UUID(str(conversation_id)))
    if conversation is None or conversation.user_id != ctx.user_id:
        return groups
    messages = await db.scalars(select(Message).where(
        Message.conversation_id == conversation.id, Message.role == 'user', Message.attachments.is_not(None),
    ).order_by(Message.position.desc()).limit(100))
    groups.extend([[a.get('id') for a in message.attachments or [] if isinstance(a, dict) and a.get('id')]
                   for message in messages])
    return groups


def ambiguity(matches):
    choices = [{'document_id': str(d.id), 'filename': d.title} for d in matches[:10]]
    raise ValueError('Multiple uploaded copies match. Attach just the intended workbook to this message; '
                     'the current attachment will take priority. Otherwise select from these known documents: ' + json.dumps(choices))


async def resolve(db, model, owner, document_id, path, groups=()):
    if document_id:
        document = await db.get(model, uuid.UUID(str(document_id)))
        if document is None or document.user_id != owner or document.file_type != 'xlsx' or not document.storage_key:
            raise ValueError('Workbook is unavailable to this account.')
        return document
    name = engine.filename(path)
    normalized_groups = []
    for group in groups:
        ids = set()
        for value in group:
            try:
                ids.add(uuid.UUID(str(value)))
            except (ValueError, TypeError, AttributeError):
                continue
        normalized_groups.append(ids)
    identifiers = set().union(*normalized_groups) if normalized_groups else set()
    if identifiers:
        linked = list(await db.scalars(select(model).where(
            model.user_id == owner, model.file_type == 'xlsx', model.title == name,
            model.storage_key.is_not(None), model.id.in_(identifiers),
        )))
        linked = [d for d in linked if d.storage_key]
        for group in normalized_groups:
            matches = [d for d in linked if d.id in group]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                ambiguity(matches)
    matches = list(await db.scalars(select(model).where(model.user_id == owner, model.file_type == 'xlsx',
                                                        model.title == name).limit(11)))
    matches = [d for d in matches if d.storage_key]
    if not matches:
        raise ValueError(f'Upload {name} to Dhanz first. A Windows/OneDrive path alone is not accessible from AWS; no local or server filesystem path was opened.')
    if len(matches) != 1:
        ambiguity(matches)
    return matches[0]


@contextlib.contextmanager
def processing_lock(settings):
    root = Path(settings.storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / '.workbook-copy.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another large workbook copy is running. Wait for it to finish, then retry.') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def install():
    from app.services import assistant_tools as tools
    from dhanz_ai import ToolSpec

    async def run(ctx, args):
        from fastapi import HTTPException
        from app.models import KnowledgeDocument, User
        from app.services.files_service import build_files_runtime, store_upload

        try:
            if ctx.settings is None:
                raise ValueError('Workbook storage is unavailable.')
            filename = args.get('filename', 'Copied_workbook.xlsx')
            if not isinstance(filename, str) or len(filename) > 150 or filename != engine.filename(filename) or '/' in filename or '\\' in filename:
                raise ValueError('Use a plain .xlsx output filename without a directory.')
            signature = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
            cache = getattr(ctx, '_workbook_copy_results', {})
            if signature in cache:
                return cache[signature]
            if len(cache) >= 2:
                raise ValueError('Create at most two bulk workbook copies per reply.')
            async with ctx.maker() as db:
                user = await db.get(User, ctx.user_id)
                if user is None or not user.is_active:
                    raise ValueError('Account is unavailable.')
                groups = await context_groups(db, ctx)
                source = await resolve(db, KnowledgeDocument, ctx.user_id, args.get('source_document_id'), args.get('source_path'), groups)
                destination = await resolve(db, KnowledgeDocument, ctx.user_id, args.get('destination_document_id'), args.get('destination_path'), groups)
                files = getattr(ctx, 'files', None) or build_files_runtime(ctx.settings)
                with processing_lock(ctx.settings):
                    source_data = await files.storage.get(source.storage_key)
                    destination_data = await files.storage.get(destination.storage_key)
                    options = {key: args[key] for key in (
                        'source_sheet', 'source_header', 'destination_sheet', 'destination_header',
                        'source_header_row', 'destination_header_row', 'overwrite',
                    ) if key in args}
                    output, summary = await asyncio.to_thread(engine.copy_column, source_data, destination_data, **options)
                    new = await store_upload(db, ctx.settings, files, None, user_id=ctx.user_id, filename=filename,
                                             data=output, project_id=destination.project_id)
                    await db.commit()
                result = tools.ToolOutcome(
                    {'created': True, 'document_id': str(new.id), 'filename': new.title, 'originals_preserved': True,
                     **summary, 'note': 'The full column was copied server-side into an attached workbook; no row data was truncated to the chat preview.'},
                    'Copied complete Excel column',
                    {'type': 'download_file', 'id': str(new.id), 'filename': new.title, 'file_type': 'xlsx'},
                )
                cache[signature] = result
                ctx._workbook_copy_results = cache
                return result
        except HTTPException as exc:
            raise tools.ToolInputError(str(exc.detail)) from None
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise tools.ToolInputError(str(exc)) from None

    tools.TOOLS['copy_workbook_column'] = tools.Tool(
        ToolSpec(
            name='copy_workbook_column',
            description='Copy an entire named column between two account-owned uploaded XLSX workbooks in one server operation. Use for Tool ID to LID and other large transfers, not repeated chat previews or manually listing values. The source is streamed without a total populated-cell cap; source ZIP/expanded bytes and text/style metadata are bounded. The copied column must fit 100000 rows including headers and 200000 destination cells. Unrelated source worksheets and columns do not count as destination cells. Paths only match uploaded filenames; they cannot open a Windows PC, OneDrive, arbitrary server path or URL. Both workbooks must be uploaded. Originals are preserved and a downloadable edited copy is attached.',
            parameters={
                'type': 'object', 'additionalProperties': False,
                'required': ['source_sheet', 'source_header', 'destination_sheet', 'destination_header'],
                'properties': {
                    **{name: {'type': 'string', 'description': description} for name, description in {
                        'source_document_id': 'Owned source XLSX UUID. Prefer this over a filename when known.',
                        'source_path': 'Uploaded source filename or Windows/OneDrive path used only to match its basename.',
                        'destination_document_id': 'Owned destination/template XLSX UUID. Prefer this when known.',
                        'destination_path': 'Uploaded destination/template filename, or path label to match its basename.',
                        'source_sheet': 'Exact source worksheet name, e.g. SOW.',
                        'source_header': 'Source heading, e.g. Tool ID. Matched ignoring case and repeated whitespace.',
                        'destination_sheet': 'Exact destination/template worksheet name.',
                        'destination_header': 'Destination heading, e.g. LID.',
                        'filename': 'Plain output .xlsx filename. Default Copied_workbook.xlsx.',
                    }.items()},
                    'source_header_row': {'type': 'integer', 'minimum': 1, 'maximum': 100000, 'description': 'Optional explicit header row; otherwise find a unique heading in the first 50 rows.'},
                    'destination_header_row': {'type': 'integer', 'minimum': 1, 'maximum': 100000},
                    'overwrite': {'type': 'boolean', 'description': 'Default false. Set true only when the user authorized replacing actual conflicting destination data.'},
                },
            },
        ), 'Copying Excel column', run,
    )
    chat = sys.modules.get('app.services.chat_service')
    original = getattr(chat, 'build_system_prompt', None)
    if original and not getattr(original, '_bulk_workbook_guidance', False):
        @functools.wraps(original)
        def prompt(*args, **kwargs):
            text = original(*args, **kwargs)
            if kwargs.get('tools'):
                text += ('\nFor complete column transfers between uploaded Excel workbooks, use copy_workbook_column. '
                         'The 500-cell inspection output is a preview limit, not the copy processing limit. '
                         'The source may exceed the ordinary inspect/edit limit; the bulk tool finds its headings without a full-source inspection first. '
                         'There is no 500000-cell source cap in this tool. Do not propose row batching for that obsolete limit; call the streaming copy tool. '
                         'External workbook links in a read-only source do not block this tool: it uses stored values without loading or following those links. '
                         'It does not remove or transfer external links; destination editing remains strict. '
                         'Do not ask the user to reduce to 20/50 rows or manually transcribe IDs when the bulk tool supports the task. '
                         'Give source/destination document IDs or uploaded filename labels and sheet/header names; let the server read all rows. '
                         'Preserve blank row positions and leading zeros. Only report the actual rows_copied returned by the tool. '
                         'A C:\\ or OneDrive path does not grant cloud access: if not uploaded, request upload of the named workbook. '
                         'Never claim to open a local path or sync OneDrive without an actual authorized connector. '
                         'For duplicate filenames, the bulk tool automatically prefers this message\'s matching attachment, '
                         'then the most recent matching attachment in this conversation. Pass the filename to let it resolve. '
                         'Do not claim duplicates prevent copying before calling the tool. '
                         'If the tool still reports ambiguity, ask the user to attach just the intended file, not to find a hidden document ID.')
            return text
        prompt._bulk_workbook_guidance = True
        chat.build_system_prompt = prompt
