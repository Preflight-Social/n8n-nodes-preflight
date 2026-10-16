"""Builds the five example workflows in templates/*.json.

Run with `python3 templates/build.py`. Each template is plain n8n workflow
JSON: import it with "Import from File" (or paste it onto the canvas), then
pick your Preflight credential and your channels.

With `--test <dir> --channels <a,b> --video-channels <a,b,c> --video <file>`
it also writes test copies where third-party services (OpenAI, Google Sheets,
Notion, Slack, Telegram) are replaced by fixed sample data and every Preflight
post is a draft, so the Preflight part can be run end to end without
anything going live. Channels are "platform:channelId" values from your own
workspace.
"""

import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).parent
PREFLIGHT = 'n8n-nodes-preflight.preflight'
PREFLIGHT_TRIGGER = 'n8n-nodes-preflight.preflightTrigger'


def nid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'preflight-template/{name}'))


class Workflow:
    def __init__(self, name: str, slug: str):
        self.name = name
        self.slug = slug
        self.nodes: list[dict] = []
        self.connections: dict = {}

    def node(self, name, type_, params, version=1, x=0, y=0, **extra):
        node = {
            'parameters': params,
            'id': nid(f'{self.slug}/{name}'),
            'name': name,
            'type': type_,
            'typeVersion': version,
            'position': [x, y],
        }
        node.update(extra)
        self.nodes.append(node)
        return name

    def note(self, name, text, x, y, width=420, height=320, color=None):
        params = {'content': text, 'height': height, 'width': width}
        if color:
            params['color'] = color
        return self.node(name, 'n8n-nodes-base.stickyNote', params, 1, x, y)

    def link(self, a, b, output=0, kind='main'):
        outputs = self.connections.setdefault(a, {}).setdefault(kind, [])
        while len(outputs) <= output:
            outputs.append([])
        outputs[output].append({'node': b, 'type': kind, 'index': 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def replace(self, name, type_, params, version=1):
        for node in self.nodes:
            if node['name'] == name:
                node['type'] = type_
                node['typeVersion'] = version
                node['parameters'] = params
                node.pop('credentials', None)
                node.pop('webhookId', None)
                return
        raise KeyError(name)

    def params(self, name):
        return next(node for node in self.nodes if node['name'] == name)['parameters']

    def drop_connections_of(self, name, kind):
        for source, kinds in list(self.connections.items()):
            if kind in kinds and any(t['node'] == name for out in kinds[kind] for t in out):
                del kinds[kind]
            if not kinds:
                del self.connections[source]

    def remove(self, name):
        self.nodes = [n for n in self.nodes if n['name'] != name]
        self.connections.pop(name, None)
        for kinds in self.connections.values():
            for outs in kinds.values():
                for out in outs:
                    out[:] = [t for t in out if t['node'] != name]

    def json(self):
        return {
            'name': self.name,
            'nodes': self.nodes,
            'connections': self.connections,
            'pinData': {},
            'settings': {'executionOrder': 'v1'},
            'meta': {'templateCredsSetupCompleted': False},
            'tags': [],
        }


def if_ok(field='={{ $json.ok }}'):
    return {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict', 'version': 2},
            'conditions': [
                {
                    'id': nid(field),
                    'leftValue': field,
                    'rightValue': '',
                    'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True},
                }
            ],
            'combinator': 'and',
        },
        'options': {},
    }


def if_not_empty(field):
    return {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 2},
            'conditions': [
                {
                    'id': nid(field),
                    'leftValue': field,
                    'rightValue': '',
                    'operator': {'type': 'string', 'operation': 'notEmpty', 'singleValue': True},
                }
            ],
            'combinator': 'and',
        },
        'looseTypeValidation': True,
        'options': {},
    }


ISSUES = "={{ $json.issues.map(i => (i.platform ? i.platform + ': ' : '') + i.message).join('\\n') }}"


# ---------------------------------------------------------------------------
# 1. RSS / blog -> AI caption -> Preflight validate -> draft
# ---------------------------------------------------------------------------
def rss_to_drafts() -> Workflow:
    w = Workflow('Blog RSS to AI-written social drafts, checked by Preflight', 'rss')
    w.note(
        'About',
        '## Blog RSS → AI caption → Preflight drafts\n\n'
        'Every hour, new articles from your feed get a short social caption from an AI model. '
        'Preflight checks the caption against every chosen network\'s publishing rules '
        '(length counted the network\'s way, links, hashtags, media). Posts that pass land in '
        'Preflight as **drafts** for a person to approve. Nothing is published.\n\n'
        '**Set up**\n1. Put your feed URL in **Read feed**.\n2. Add an OpenAI credential to **OpenAI model** '
        '(or swap in any chat model).\n3. In both Preflight nodes pick your Preflight credential and the same channels.\n\n'
        'The idempotency key is a hash of the article link, so an article never becomes two drafts.',
        -520, -240, 460, 420,
    )
    w.node('Every hour', 'n8n-nodes-base.scheduleTrigger',
           {'rule': {'interval': [{'field': 'hours', 'hoursInterval': 1}]}}, 1.2, 0, 0)
    w.node('Read feed', 'n8n-nodes-base.rssFeedRead',
           {'url': 'https://preflight.social/blog/feed.xml', 'options': {}}, 1.2, 220, 0)
    w.node('Only new articles', 'n8n-nodes-base.removeDuplicates',
           {'operation': 'removeItemsSeenInPreviousExecutions', 'dedupeValue': '={{ $json.link }}', 'options': {}}, 2, 440, 0)
    w.node('At most 3 per run', 'n8n-nodes-base.limit', {'maxItems': 3}, 1, 660, 0)
    w.node('Write caption', '@n8n/n8n-nodes-langchain.chainLlm', {
        'promptType': 'define',
        'text': '=Write one social media post that makes people want to read this article.\n\n'
                'Title: {{ $json.title }}\nSummary: {{ $json.contentSnippet }}\n\n'
                'Rules: under 250 characters, plain text, at most two hashtags, no emoji at the start, '
                'and do not include the link (it is added separately). Reply with the post text only.',
    }, 1.7, 880, 0)
    w.node('OpenAI model', '@n8n/n8n-nodes-langchain.lmChatOpenAi', {
        'model': {'__rl': True, 'value': 'gpt-4o-mini', 'mode': 'list', 'cachedResultName': 'gpt-4o-mini'},
        'options': {},
    }, 1.2, 880, 200)
    channels = []
    w.node('Check against network rules', PREFLIGHT, {
        'resource': 'post', 'operation': 'validate', 'channels': channels,
        'content': '={{ $json.text.trim() }}',
        'additionalFields': {'linkUrl': "={{ $('Only new articles').item.json.link }}"},
    }, 1, 1240, 0)
    w.node('Passes every network?', 'n8n-nodes-base.if', if_ok(), 2.2, 1460, 0)
    w.node('Save as draft in Preflight', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', 'channels': channels,
        'content': "={{ $('Write caption').item.json.text.trim() }}",
        'when': 'draft',
        'idempotencyKey': "={{ 'rss-' + $('Only new articles').item.json.link.hash('sha256') }}",
        'additionalFields': {'linkUrl': "={{ $('Only new articles').item.json.link }}"},
    }, 1, 1680, -100)
    w.node('Needs a human', 'n8n-nodes-base.set', {
        'assignments': {'assignments': [
            {'id': nid('rss-title'), 'name': 'article', 'value': "={{ $('Only new articles').item.json.title }}", 'type': 'string'},
            {'id': nid('rss-issues'), 'name': 'issues', 'value': ISSUES, 'type': 'string'},
        ]},
        'options': {},
    }, 3.4, 1680, 100)
    w.chain('Every hour', 'Read feed', 'Only new articles', 'At most 3 per run', 'Write caption',
            'Check against network rules', 'Passes every network?')
    w.link('OpenAI model', 'Write caption', kind='ai_languageModel')
    w.link('Passes every network?', 'Save as draft in Preflight', 0)
    w.link('Passes every network?', 'Needs a human', 1)
    return w


# ---------------------------------------------------------------------------
# 2. Google Sheets content calendar -> Preflight
# ---------------------------------------------------------------------------
SHEET_COLUMNS = 'Text | Channels | Publish At | Media URL | Link | Status | Preflight Post ID | Issues'


def sheets_calendar() -> Workflow:
    w = Workflow('Google Sheets content calendar to Preflight, checked before scheduling', 'sheets')
    w.note(
        'About',
        '## Google Sheets content calendar → Preflight\n\n'
        'Write posts in a sheet, set **Status** to `Ready`, and every 15 minutes they are checked '
        'against each network\'s rules and scheduled in Preflight. The row gets the Preflight post ID '
        'and `Scheduled`, or `Needs fix` with the exact reason (e.g. "24 characters over on Bluesky").\n\n'
        f'**Sheet columns**\n`{SHEET_COLUMNS}`\n\n'
        '- **Channels**: network names, comma-separated, e.g. `bluesky, mastodon, linkedin` '
        '(or `platform:channelId` when you have two of one network).\n'
        '- **Publish At**: `2026-11-02 09:30` in the workflow\'s time zone. Empty = next free queue slot.\n'
        '- **Media URL**: optional public link to an image or video.\n\n'
        'Pick the sheet in all three Google Sheets nodes and your Preflight credential in the Preflight nodes.',
        -560, -300, 500, 480,
    )
    w.node('Every 15 minutes', 'n8n-nodes-base.scheduleTrigger',
           {'rule': {'interval': [{'field': 'minutes', 'minutesInterval': 15}]}}, 1.2, 0, 0)
    sheet = {'__rl': True, 'value': '', 'mode': 'list'}
    w.node('Rows marked Ready', 'n8n-nodes-base.googleSheets', {
        'documentId': sheet, 'sheetName': {'__rl': True, 'value': '', 'mode': 'list'},
        'filtersUI': {'values': [{'lookupColumn': 'Status', 'lookupValue': 'Ready'}]},
        'options': {},
    }, 4.7, 220, 0)
    w.node('Has a file?', 'n8n-nodes-base.if', if_not_empty("={{ $json['Media URL'] }}"), 2.2, 440, 0)
    w.node('Upload file to Preflight', PREFLIGHT, {
        'resource': 'media', 'operation': 'upload', 'source': 'url',
        'sourceUrl': "={{ $json['Media URL'] }}", 'kind': 'auto', 'waitUntilReady': True,
    }, 1, 660, -100)
    w.node('Together again', 'n8n-nodes-base.merge', {}, 3.2, 880, 0)
    row = "$('Rows marked Ready').item.json"
    post_fields = {
        'channels': f"={{{{ {row}.Channels }}}}",
        'content': f"={{{{ {row}.Text }}}}",
        'additionalFields': {
            'mediaIds': "={{ $json.kind ? $json.id : '' }}",
            'linkUrl': f"={{{{ {row}.Link }}}}",
        },
    }
    w.node('Check against network rules', PREFLIGHT, {'resource': 'post', 'operation': 'validate', **post_fields}, 1, 1100, 0)
    w.node('Passes every network?', 'n8n-nodes-base.if', if_ok(), 2.2, 1320, 0)
    w.node('Has a time?', 'n8n-nodes-base.if', if_not_empty(f"={{{{ {row}['Publish At'] }}}}"), 2.2, 1540, -120)
    w.node('Schedule in Preflight', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **post_fields,
        'when': 'scheduled', 'scheduledAt': f"={{{{ {row}['Publish At'] }}}}",
        'idempotencyKey': f"={{{{ 'sheet-' + $('Rows marked Ready').item.json.row_number + '-' + {row}.Text.hash('sha256') }}}}",
    }, 1, 1760, -220)
    w.node('Queue in Preflight', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **post_fields,
        'when': 'queue',
        'idempotencyKey': f"={{{{ 'sheet-' + $('Rows marked Ready').item.json.row_number + '-' + {row}.Text.hash('sha256') }}}}",
    }, 1, 1760, -40)
    update = lambda status, extra: {
        'operation': 'update', 'documentId': sheet, 'sheetName': {'__rl': True, 'value': '', 'mode': 'list'},
        'columns': {
            'mappingMode': 'defineBelow',
            'value': {'row_number': f"={{{{ {row}.row_number }}}}", 'Status': status, **extra},
            'matchingColumns': ['row_number'],
            'schema': [],
        },
        'options': {},
    }
    w.node('Mark Scheduled', 'n8n-nodes-base.googleSheets',
           update('Scheduled', {'Preflight Post ID': '={{ $json.id }}', 'Issues': ''}), 4.7, 1980, -120)
    w.node('Mark Needs fix', 'n8n-nodes-base.googleSheets',
           update('Needs fix', {'Issues': ISSUES}), 4.7, 1540, 140)
    w.chain('Every 15 minutes', 'Rows marked Ready', 'Has a file?')
    w.link('Has a file?', 'Upload file to Preflight', 0)
    w.link('Upload file to Preflight', 'Together again')
    w.connections['Has a file?']['main'][1:] = [[{'node': 'Together again', 'type': 'main', 'index': 1}]]
    w.chain('Together again', 'Check against network rules', 'Passes every network?')
    w.link('Passes every network?', 'Has a time?', 0)
    w.link('Passes every network?', 'Mark Needs fix', 1)
    w.link('Has a time?', 'Schedule in Preflight', 0)
    w.link('Has a time?', 'Queue in Preflight', 1)
    w.link('Schedule in Preflight', 'Mark Scheduled')
    w.link('Queue in Preflight', 'Mark Scheduled')
    w.params('Together again').update({'mode': 'append'})
    return w


# ---------------------------------------------------------------------------
# 3. One vertical video -> YouTube Shorts, Instagram Reels, TikTok
# ---------------------------------------------------------------------------
def video_to_shorts() -> Workflow:
    w = Workflow('One vertical video to YouTube Shorts, Instagram Reels and TikTok with Preflight', 'shorts')
    w.note(
        'About',
        '## One vertical video → Shorts, Reels and TikTok\n\n'
        'Drop a vertical video into the form. Preflight checks it against each network\'s video rules '
        '(length, size, frame rate, aspect ratio, caption length) **before** uploading anywhere, then '
        'queues it for the next free slot on each channel.\n\n'
        '- YouTube: published as a Short with the title from the form.\n'
        '- Instagram: as a Reel.\n'
        '- TikTok: sent to the creator\'s **inbox** to finish in the app (privacy Only me). '
        'Change the TikTok options when you are ready to post directly.\n\n'
        'Starting from a long YouTube video? Cut the vertical clip first; downloading videos from '
        'YouTube is against its terms. A Google Drive or Dropbox trigger works in place of the form.\n\n'
        'The form is protected with **Basic Auth**: create a login for it in **Upload form**, '
        'otherwise anyone with the form link could queue videos to your channels.\n\n'
        'Pick your Preflight credential and the three channels in the Preflight nodes.',
        -560, -360, 500, 560,
    )
    w.node('Upload form', 'n8n-nodes-base.formTrigger', {
        'formTitle': 'New short video',
        'formDescription': 'Checked by Preflight, then queued to YouTube Shorts, Instagram Reels and TikTok.',
        'formFields': {'values': [
            {'fieldLabel': 'Video', 'fieldType': 'file', 'multipleFiles': False,
             'acceptFileTypes': '.mp4, .mov', 'requiredField': True},
            {'fieldLabel': 'Caption', 'fieldType': 'textarea', 'requiredField': True},
            {'fieldLabel': 'YouTube title', 'requiredField': True},
        ]},
        'authentication': 'basicAuth',
        'responseMode': 'lastNode',
        'options': {},
    }, 2.2, 0, 0, webhookId=nid('shorts-form'),
       credentials={'httpBasicAuth': {'id': '', 'name': 'Upload form login'}})
    w.node('Upload video to Preflight', PREFLIGHT, {
        'resource': 'media', 'operation': 'upload', 'source': 'binary',
        'binaryPropertyName': 'Video', 'kind': 'video', 'waitUntilReady': True,
        'options': {'waitTimeout': 900},
    }, 1, 220, 0)
    form = "$('Upload form').item.json"
    fields = {
        'channels': [],
        'content': f"={{{{ {form}.Caption }}}}",
        'additionalFields': {'mediaIds': '={{ $json.id }}'},
        'networkOptions': {
            'youtubeTitle': f"={{{{ {form}['YouTube title'] }}}}",
            'youtubeShort': True,
            'youtubePrivacy': 'public',
            'instagramPlacement': 'reel',
            'tiktokPrivacy': 'SELF_ONLY',
            'tiktokAsDraft': True,
        },
    }
    w.node('Check video rules', PREFLIGHT, {'resource': 'post', 'operation': 'validate', **fields}, 1, 440, 0)
    w.node('Passes every network?', 'n8n-nodes-base.if', if_ok(), 2.2, 660, 0)
    w.node('Queue on every channel', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **fields,
        'additionalFields': {'mediaIds': "={{ $('Upload video to Preflight').item.json.id }}"},
        'when': 'queue',
        'idempotencyKey': "={{ 'short-' + $('Upload video to Preflight').item.json.id }}",
    }, 1, 880, -100)
    w.node('Queued', 'n8n-nodes-base.form', {
        'operation': 'completion',
        'completionTitle': 'Queued',
        'completionMessage': "=It goes out on each channel at its next free slot. Preflight post {{ $json.id }}.",
    }, 1, 1100, -100, webhookId=nid('shorts-done'))
    w.node('Refused', 'n8n-nodes-base.form', {
        'operation': 'completion',
        'completionTitle': 'Not queued: fix this first',
        'completionMessage': ISSUES,
    }, 1, 880, 100, webhookId=nid('shorts-refused'))
    w.chain('Upload form', 'Upload video to Preflight', 'Check video rules', 'Passes every network?')
    w.link('Passes every network?', 'Queue on every channel', 0)
    w.link('Passes every network?', 'Refused', 1)
    w.link('Queue on every channel', 'Queued')
    return w


# ---------------------------------------------------------------------------
# 4. Notion database -> Preflight
# ---------------------------------------------------------------------------
def notion_calendar() -> Workflow:
    w = Workflow('Notion content database to Preflight, checked before scheduling', 'notion')
    w.note(
        'About',
        '## Notion database → Preflight\n\n'
        'Plan posts in a Notion database. Every 15 minutes, pages with **Status** = `Ready` are checked '
        'against each network\'s rules and scheduled in Preflight. The page then gets `Scheduled` and the '
        'Preflight post ID, or `Needs fix` and the reason.\n\n'
        '**Database properties**\n'
        '- `Name` (title) - internal name\n- `Text` (text) - the caption\n'
        '- `Channels` (text) - e.g. `bluesky, linkedin`\n- `Publish At` (date with time)\n'
        '- `Media URL` (URL, optional)\n- `Status` (status: Ready, Scheduled, Needs fix)\n'
        '- `Preflight ID` (text)\n- `Issues` (text)\n\n'
        'Pick the database in all three Notion nodes and your Preflight credential in the Preflight nodes.',
        -560, -320, 500, 500,
    )
    w.node('Every 15 minutes', 'n8n-nodes-base.scheduleTrigger',
           {'rule': {'interval': [{'field': 'minutes', 'minutesInterval': 15}]}}, 1.2, 0, 0)
    db = {'__rl': True, 'value': '', 'mode': 'list'}
    w.node('Pages marked Ready', 'n8n-nodes-base.notion', {
        'resource': 'databasePage', 'operation': 'getAll', 'databaseId': db, 'returnAll': True,
        'filterType': 'manual',
        'filters': {'conditions': [{'key': 'Status|status', 'condition': 'equals', 'statusValue': 'Ready'}]},
        'options': {},
    }, 2.2, 220, 0)
    w.node('Has a file?', 'n8n-nodes-base.if', if_not_empty('={{ $json.property_media_url }}'), 2.2, 440, 0)
    w.node('Upload file to Preflight', PREFLIGHT, {
        'resource': 'media', 'operation': 'upload', 'source': 'url',
        'sourceUrl': '={{ $json.property_media_url }}', 'kind': 'auto', 'waitUntilReady': True,
    }, 1, 660, -100)
    w.node('Together again', 'n8n-nodes-base.merge', {'mode': 'append'}, 3.2, 880, 0)
    page = "$('Pages marked Ready').item.json"
    fields = {
        'channels': f'={{{{ {page}.property_channels }}}}',
        'content': f'={{{{ {page}.property_text }}}}',
        'additionalFields': {'mediaIds': "={{ $json.kind ? $json.id : '' }}"},
    }
    w.node('Check against network rules', PREFLIGHT, {'resource': 'post', 'operation': 'validate', **fields}, 1, 1100, 0)
    w.node('Passes every network?', 'n8n-nodes-base.if', if_ok(), 2.2, 1320, 0)
    w.node('Schedule in Preflight', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **fields,
        'when': 'scheduled', 'scheduledAt': f'={{{{ {page}.property_publish_at.start }}}}',
        'idempotencyKey': f"={{{{ 'notion-' + {page}.id + '-' + {page}.property_text.hash('sha256') }}}}",
    }, 1, 1540, -100)
    status = lambda value, extra: {
        'resource': 'databasePage', 'operation': 'update',
        'pageId': {'__rl': True, 'value': f'={{{{ {page}.id }}}}', 'mode': 'id'},
        'propertiesUi': {'propertyValues': [{'key': 'Status|status', 'statusValue': value}, *extra]},
        'options': {},
    }
    w.node('Mark Scheduled', 'n8n-nodes-base.notion', status('Scheduled', [
        {'key': 'Preflight ID|rich_text', 'textContent': '={{ $json.id }}'},
    ]), 2.2, 1760, -100)
    w.node('Mark Needs fix', 'n8n-nodes-base.notion', status('Needs fix', [
        {'key': 'Issues|rich_text', 'textContent': ISSUES},
    ]), 2.2, 1540, 100)
    w.chain('Every 15 minutes', 'Pages marked Ready', 'Has a file?')
    w.link('Has a file?', 'Upload file to Preflight', 0)
    w.link('Upload file to Preflight', 'Together again')
    w.connections['Has a file?']['main'][1:] = [[{'node': 'Together again', 'type': 'main', 'index': 1}]]
    w.chain('Together again', 'Check against network rules', 'Passes every network?')
    w.link('Passes every network?', 'Schedule in Preflight', 0)
    w.link('Passes every network?', 'Mark Needs fix', 1)
    w.link('Schedule in Preflight', 'Mark Scheduled')
    return w


# ---------------------------------------------------------------------------
# 5. post.failed -> Slack and Telegram alert
# ---------------------------------------------------------------------------
def failed_alerts() -> Workflow:
    w = Workflow('Alert Slack and Telegram when a Preflight post fails', 'alerts')
    w.note(
        'About',
        '## Failed post → Slack and Telegram\n\n'
        'Preflight sends `post.failed` once it has stopped retrying a channel, so this fires once per real '
        'failure, not on every attempt. The alert says which network, why, whether a retry can work, and '
        'links straight to the post in Preflight.\n\n'
        'Keep the branch you use and delete the other.\n\n'
        '**Set up**: Preflight credential with webhooks:read and webhooks:write scopes, then activate. '
        'Preflight only delivers to a public https URL, so a local n8n needs a tunnel.',
        -560, -280, 460, 380,
    )
    w.node('When a post fails', PREFLIGHT_TRIGGER, {'events': ['post.failed']},
           1, 0, 0, webhookId=nid('alerts-trigger'))
    w.node('Get the post', PREFLIGHT, {'resource': 'post', 'operation': 'get', 'postId': '={{ $json.postId }}'}, 1, 220, 0)
    msg = (
        "={{ '⚠️ Preflight: post failed on ' + $('When a post fails').item.json.platform + '\\n' + "
        "'Why: ' + $('When a post fails').item.json.error + '\\n' + "
        "($('When a post fails').item.json.permanent ? 'Retrying will not help until this is fixed.' : 'A retry may work.') + '\\n' + "
        "'Text: ' + ($json.content || '').slice(0, 140) + '\\n' + "
        "'Open: https://preflight.social/posts?post=' + $json.id }}"
    )
    w.node('Write alert', 'n8n-nodes-base.set', {
        'assignments': {'assignments': [{'id': nid('alert-msg'), 'name': 'message', 'value': msg, 'type': 'string'}]},
        'options': {},
    }, 3.4, 440, 0)
    w.node('Send to Slack', 'n8n-nodes-base.slack', {
        'select': 'channel', 'channelId': {'__rl': True, 'value': '', 'mode': 'list'},
        'text': '={{ $json.message }}', 'otherOptions': {},
    }, 2.3, 660, -100, webhookId=nid('alerts-slack'))
    w.node('Send to Telegram', 'n8n-nodes-base.telegram', {
        'chatId': '', 'text': '={{ $json.message }}', 'additionalFields': {'appendAttribution': False},
    }, 1.2, 660, 100, webhookId=nid('alerts-telegram'))
    w.chain('When a post fails', 'Get the post', 'Write alert')
    w.link('Write alert', 'Send to Slack')
    w.link('Write alert', 'Send to Telegram')
    return w


TEMPLATES = [
    ('01-rss-ai-caption-validate-draft', rss_to_drafts),
    ('02-google-sheets-content-calendar', sheets_calendar),
    ('03-vertical-video-shorts-reels-tiktok', video_to_shorts),
    ('04-notion-database-to-preflight', notion_calendar),
    ('05-failed-post-slack-telegram-alert', failed_alerts),
]


# Set by --video and --video-channels when writing test copies.
VIDEO_CHANNELS: list[str] = []
VIDEO = ''


def code(js):
    return {'jsCode': js}


def test_copy(slug: str, w: Workflow, channels: list[str]) -> Workflow:
    """Same workflow with external services replaced and only drafts created."""
    cred = {'preflightApi': {'id': 'pfcred0000000001', 'name': 'Preflight account'}}
    for node in w.nodes:
        if node['type'] in (PREFLIGHT, PREFLIGHT_TRIGGER):
            node['credentials'] = cred
            p = node['parameters']
            if 'channels' in p and p['channels'] == []:
                p['channels'] = VIDEO_CHANNELS if slug.startswith('03') else channels
            if p.get('operation') == 'create':
                p['when'] = 'draft'
                p.pop('scheduledAt', None)
                p['idempotencyKey'] = '={{ $execution.id }}-{{ $itemIndex }}'
    if slug.startswith('01'):
        w.replace('Every hour', 'n8n-nodes-base.manualTrigger', {})
        w.params('At most 3 per run')['maxItems'] = 1
        w.drop_connections_of('Write caption', 'ai_languageModel')
        w.remove('OpenAI model')
        w.replace('Write caption', 'n8n-nodes-base.code', code(
            "return $input.all().map(i => ({ json: { text: 'TEST-n8n template 1: ' + i.json.title + ' #preflight' } }));"), 2)
    if slug.startswith('02'):
        w.replace('Every 15 minutes', 'n8n-nodes-base.manualTrigger', {})
        w.replace('Rows marked Ready', 'n8n-nodes-base.code', code(
            "return [\n"
            "  { json: { row_number: 2, Text: 'TEST-n8n template 2: row with a picture', Channels: 'bluesky, mastodon', 'Publish At': '2026-12-01 09:30', 'Media URL': 'https://preflight.social/og-image.jpg', Link: 'https://preflight.social', Status: 'Ready' } },\n"
            "  { json: { row_number: 3, Text: 'TEST-n8n template 2: ' + 'far too long for Bluesky. '.repeat(14), Channels: 'bluesky', 'Publish At': '', 'Media URL': '', Link: '', Status: 'Ready' } },\n"
            "];"), 2)
        w.replace('Mark Scheduled', 'n8n-nodes-base.noOp', {})
        w.replace('Mark Needs fix', 'n8n-nodes-base.set', {
            'assignments': {'assignments': [{'id': nid('t2-issues'), 'name': 'Issues', 'value': ISSUES, 'type': 'string'}]},
            'options': {}}, 3.4)
    if slug.startswith('03'):
        w.nodes.insert(0, {
            'parameters': {'operation': 'read', 'fileSelector': VIDEO, 'options': {}},
            'id': nid('t3-read'), 'name': 'Read test video', 'type': 'n8n-nodes-base.readWriteFile',
            'typeVersion': 1, 'position': [-440, 0],
        })
        w.nodes.insert(0, {'parameters': {}, 'id': nid('t3-start'), 'name': 'Start', 'type': 'n8n-nodes-base.manualTrigger', 'typeVersion': 1, 'position': [-660, 0]})
        w.replace('Upload form', 'n8n-nodes-base.code', code(
            "return $input.all().map(i => ({ json: { Caption: 'TEST-n8n template 3 vertical video #shorts', 'YouTube title': 'TEST-n8n template 3' }, binary: { Video: i.binary.data } }));"), 2)
        w.link('Start', 'Read test video')
        w.link('Read test video', 'Upload form')
        w.replace('Queued', 'n8n-nodes-base.noOp', {})
        w.replace('Refused', 'n8n-nodes-base.set', {
            'assignments': {'assignments': [{'id': nid('t3-issues'), 'name': 'Issues', 'value': ISSUES, 'type': 'string'}]},
            'options': {}}, 3.4)
    if slug.startswith('04'):
        w.replace('Every 15 minutes', 'n8n-nodes-base.manualTrigger', {})
        w.replace('Pages marked Ready', 'n8n-nodes-base.code', code(
            "return [{ json: { id: '1a2b3c4d-0000-4000-8000-000000000001', name: 'Test page', property_text: 'TEST-n8n template 4 from Notion', property_channels: 'mastodon', property_publish_at: { start: '2026-12-01T09:30:00.000+01:00' }, property_media_url: '', property_status: 'Ready' } }];"), 2)
        w.replace('Mark Scheduled', 'n8n-nodes-base.noOp', {})
        w.replace('Mark Needs fix', 'n8n-nodes-base.noOp', {})
    if slug.startswith('05'):
        w.replace('Send to Slack', 'n8n-nodes-base.noOp', {})
        w.replace('Send to Telegram', 'n8n-nodes-base.noOp', {})
    return w


def main():
    out = HERE
    test_dir = None
    if '--test' in sys.argv:
        global VIDEO, VIDEO_CHANNELS
        arg = lambda flag: sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else ''
        test_dir = Path(arg('--test'))
        test_dir.mkdir(parents=True, exist_ok=True)
        channels = arg('--channels').split(',')
        VIDEO_CHANNELS = arg('--video-channels').split(',')
        VIDEO = arg('--video')
    for slug, build in TEMPLATES:
        w = build()
        (out / f'{slug}.json').write_text(json.dumps(w.json(), indent=2, ensure_ascii=False) + '\n')
        if test_dir:
            t = test_copy(slug, build(), channels)
            data = t.json()
            data['id'] = 'pftpl' + slug[:2] + '000000000'
            data['name'] = 'TEST ' + data['name']
            data['active'] = False
            (test_dir / f'{slug}.json').write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print('written', len(TEMPLATES))


if __name__ == '__main__':
    main()
