"""Builds the example workflows in templates/*.json.

Run with `python3 templates/build.py`. Each template is plain n8n workflow
JSON laid out the way the n8n template gallery asks for: one overview sticky
note (How it works, Setup, Customization), a short note over each group of
nodes, and a Configuration node that holds everything a user has to change.
Import a file with "Import from File" (or paste it onto the canvas), fill in
Configuration and pick the credentials.

With `--drafts <dir>` it also writes copies in which every Preflight Create
saves a draft instead of scheduling or queueing, so a template can be run
end to end against real accounts without anything going live. Nothing else
differs from the published JSON.
"""

import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).parent
PREFLIGHT = 'n8n-nodes-preflight.preflight'
PREFLIGHT_TRIGGER = 'n8n-nodes-preflight.preflightTrigger'

YELLOW, RED, WHITE = 1, 3, 7

REQUIREMENTS = (
    'Needs the verified community node **Preflight** ([n8n-nodes-preflight]'
    '(https://www.npmjs.com/package/n8n-nodes-preflight) 0.1.1 or later): search for Preflight in the '
    'nodes panel and choose Install. Tested on n8n 2.43.'
)
API_KEY = (
    'In [Preflight](https://preflight.social) (the free plan works), connect your social accounts, then '
    'create an API key under Settings → API keys'
)


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

    def note(self, name, text, x, y, width, height, color=WHITE):
        params = {'content': text, 'height': height, 'width': width, 'color': color}
        return self.node(name, 'n8n-nodes-base.stickyNote', params, 1, x, y)

    def link(self, a, b, output=0, kind='main', index=0):
        outputs = self.connections.setdefault(a, {}).setdefault(kind, [])
        while len(outputs) <= output:
            outputs.append([])
        outputs[output].append({'node': b, 'type': kind, 'index': index})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

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


def condition(field, operator):
    return {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 2},
            'conditions': [{'id': nid(field), 'leftValue': field, 'rightValue': '', 'operator': operator}],
            'combinator': 'and',
        },
        'looseTypeValidation': True,
        'options': {},
    }


def if_ok(field='={{ $json.ok }}'):
    return condition(field, {'type': 'boolean', 'operation': 'true', 'singleValue': True})


def if_not_empty(field):
    return condition(field, {'type': 'string', 'operation': 'notEmpty', 'singleValue': True})


# A Preflight node set to "On Error: Continue" passes a refusal on as an item
# with `error` (and `description`) instead of stopping the workflow; this If
# sends the items that made a post down its true branch.
SAVED = if_not_empty('={{ $json.id }}')
# Starts with a word: Google Sheets swallows a leading apostrophe, and some messages begin with one.
ERROR_TEXT = "={{ 'Error: ' + ([$json.error, $json.description].filter(Boolean).join(' ') || 'Preflight refused the post') }}"


def fields(slug, pairs, include_other=False):
    """An Edit Fields (Set) node's parameters from (name, value, type) triples."""
    params = {
        'assignments': {'assignments': [
            {'id': nid(f'{slug}/{name}'), 'name': name, 'value': value, 'type': type_}
            for name, value, type_ in pairs
        ]},
        'options': {},
    }
    if include_other:
        params['includeOtherFields'] = True
    return params


# Safe to retry: Validate changes nothing. (n8n does not retry a node whose
# errors continue as items, so nodes with onError set do not get this.)
RETRY = {'retryOnFail': True, 'maxTries': 3, 'waitBetweenTries': 5000}

ISSUES_JS = "$json.issues.map(i => (i.platform ? i.platform + ': ' : '') + i.message).join('\\n')"
ISSUES = '={{ ' + ISSUES_JS + ' }}'
CONFIG = "$('Configuration').first().json"
ERR_JS = "'Error: ' + ([$json.error, $json.description].filter(Boolean).join(' ') || 'Preflight refused the post')"


# ---------------------------------------------------------------------------
# 1. Blog RSS -> Claude caption -> Preflight validate (+ one rewrite) -> draft
# ---------------------------------------------------------------------------
def rss_to_drafts() -> Workflow:
    w = Workflow('Turn new blog posts into AI-written social drafts checked against each network\'s rules', 'rss')
    w.note(
        'Overview',
        '## Turn new blog posts into social drafts that every network accepts\n\n'
        'For content marketers who want a social post for every new article without checking each '
        'network\'s rules by hand.\n\n'
        '### How it works\n'
        '1. Every hour the workflow reads your RSS feed and keeps only articles it has not seen before.\n'
        '2. Claude writes a short caption for each one.\n'
        '3. Preflight checks the caption and the link against the rules of every channel you chose: '
        'length counted the way each network counts it, link and hashtag rules, plan limits.\n'
        '4. If a network would refuse it, Claude rewrites it once using Preflight\'s exact reasons '
        '(for example "Text is 385 characters; Bluesky allows 300.") and Preflight checks again.\n'
        '5. Captions that pass are saved in Preflight as **drafts** for a person to approve. Nothing is published.\n\n'
        '### Setup\n'
        f'1. {REQUIREMENTS}\n'
        f'2. {API_KEY} with the scopes `posts:read` and `posts:write`. That key can make drafts but can never '
        'publish. Add it as a **Preflight API** credential in the three Preflight nodes.\n'
        '3. Add an Anthropic credential to **Claude**.\n'
        '4. In **Configuration**, set your feed URL and your channels, e.g. `bluesky, mastodon, linkedin`.\n\n'
        '### Customization\n'
        '- Change the caption rules in **Write caption** (tone, hashtags, language).\n'
        '- Swap Claude for any chat model.\n'
        '- Send **Still refused** to Slack or e-mail so someone writes those by hand.',
        -760, -380, 560, 880, YELLOW,
    )
    w.note('Section: new articles', '### 1. New articles\nReads the feed and skips anything seen in an earlier run. '
           'At most three per run, so a long backlog does not flood your drafts.',
           -60, -160, 1100, 360)
    w.note('Section: caption and check', '### 2. Caption and rules check\nClaude writes the caption; Preflight '
           'answers `ok` or a list of issues per network.',
           1080, -160, 680, 520)
    w.note('Section: rewrite once', '### 3. One rewrite\nThe issues go back to Claude once. A caption that still '
           'fails stops here for a person.',
           1800, 140, 1000, 440)
    w.note('Section: save', '### 4. Save as draft\nThe idempotency key is a hash of the article link, so an '
           'article never becomes two drafts. A refused save goes to **Not saved**.',
           1800, -320, 1720, 420)

    w.node('Every hour', 'n8n-nodes-base.scheduleTrigger',
           {'rule': {'interval': [{'field': 'hours', 'hoursInterval': 1}]}}, 1.2, 0, 0)
    w.node('Configuration', 'n8n-nodes-base.set', fields('rss', [
        ('feedUrl', 'https://preflight.social/blog/feed.xml', 'string'),
        ('channels', 'bluesky, mastodon', 'string'),
    ]), 3.4, 220, 0)
    w.node('Read feed', 'n8n-nodes-base.rssFeedRead',
           {'url': f'={{{{ {CONFIG}.feedUrl }}}}', 'options': {}}, 1.2, 440, 0)
    w.node('Only new articles', 'n8n-nodes-base.removeDuplicates',
           {'operation': 'removeItemsSeenInPreviousExecutions', 'dedupeValue': '={{ $json.link }}', 'options': {}}, 2, 660, 0)
    w.node('At most 3 per run', 'n8n-nodes-base.limit', {'maxItems': 3}, 1, 880, 0)
    w.node('Write caption', '@n8n/n8n-nodes-langchain.chainLlm', {
        'promptType': 'define',
        'text': '=Write one social media post that makes people want to read this article.\n\n'
                'Title: {{ $json.title }}\nSummary: {{ $json.contentSnippet }}\n\n'
                'Rules: under 250 characters, plain text, at most two hashtags, no emoji at the start, '
                'and do not include the link (it is added separately). Reply with the post text only.',
    }, 1.7, 1120, 0)
    w.node('Claude', '@n8n/n8n-nodes-langchain.lmChatAnthropic', {
        'model': {'__rl': True, 'value': 'claude-haiku-4-5', 'mode': 'list', 'cachedResultName': 'Claude Haiku 4.5'},
        'options': {},
    }, 1.6, 1240, 220)
    channels = f'={{{{ {CONFIG}.channels }}}}'
    link = "={{ $('Only new articles').item.json.link }}"
    w.node('Check against network rules', PREFLIGHT, {
        'resource': 'post', 'operation': 'validate', 'channels': channels,
        'content': '={{ $json.text.trim() }}',
        'additionalFields': {'linkUrl': link},
    }, 1, 1440, 0, **RETRY)
    w.node('Passes every network?', 'n8n-nodes-base.if', if_ok(), 2.2, 1640, 0)
    w.node('Use first caption', 'n8n-nodes-base.set', fields('rss-first', [
        ('caption', "={{ $('Write caption').item.json.text.trim() }}", 'string'),
    ]), 3.4, 1880, -160)
    w.node('Rewrite with the reasons', '@n8n/n8n-nodes-langchain.chainLlm', {
        'promptType': 'define',
        'text': '=This social media post breaks some networks\' rules. Rewrite it so it fixes every issue below '
                'and keeps the meaning. Write one or two short sentences, under 200 characters in total, with at '
                'most two hashtags and no link. Reply with the post text only.\n\n'
                "Post: {{ $('Write caption').item.json.text.trim() }}\n\nIssues:\n{{ " + ISSUES_JS + ' }}',
    }, 1.7, 1880, 280)
    w.node('Check the rewrite', PREFLIGHT, {
        'resource': 'post', 'operation': 'validate', 'channels': channels,
        'content': '={{ $json.text.trim() }}',
        'additionalFields': {'linkUrl': link},
    }, 1, 2200, 280, **RETRY)
    w.node('Rewrite passes?', 'n8n-nodes-base.if', if_ok(), 2.2, 2420, 280)
    w.node('Use rewrite', 'n8n-nodes-base.set', fields('rss-rewrite', [
        ('caption', "={{ $('Rewrite with the reasons').item.json.text.trim() }}", 'string'),
    ]), 3.4, 2640, 220)
    w.node('Still refused', 'n8n-nodes-base.set', fields('rss-refused', [
        ('article', "={{ $('Only new articles').item.json.title }}", 'string'),
        ('issues', ISSUES, 'string'),
    ]), 3.4, 2640, 400)
    w.node('Save as draft in Preflight', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', 'channels': channels,
        'content': '={{ $json.caption }}',
        'when': 'draft',
        'idempotencyKey': "={{ 'rss-' + $('Only new articles').item.json.link.hash('sha256') }}",
        'additionalFields': {'linkUrl': link},
    }, 1, 2860, -160, onError='continueRegularOutput')
    w.node('Draft saved?', 'n8n-nodes-base.if', SAVED, 2.2, 3080, -160)
    w.node('Not saved', 'n8n-nodes-base.set', fields('rss-not-saved', [
        ('article', "={{ $('Only new articles').item.json.title }}", 'string'),
        ('error', ERROR_TEXT, 'string'),
    ]), 3.4, 3300, -60)

    w.chain('Every hour', 'Configuration', 'Read feed', 'Only new articles', 'At most 3 per run', 'Write caption',
            'Check against network rules', 'Passes every network?')
    w.link('Claude', 'Write caption', kind='ai_languageModel')
    w.link('Claude', 'Rewrite with the reasons', kind='ai_languageModel')
    w.link('Passes every network?', 'Use first caption', 0)
    w.link('Passes every network?', 'Rewrite with the reasons', 1)
    w.chain('Rewrite with the reasons', 'Check the rewrite', 'Rewrite passes?')
    w.link('Rewrite passes?', 'Use rewrite', 0)
    w.link('Rewrite passes?', 'Still refused', 1)
    w.link('Use first caption', 'Save as draft in Preflight')
    w.link('Use rewrite', 'Save as draft in Preflight')
    w.link('Save as draft in Preflight', 'Draft saved?')
    w.link('Draft saved?', 'Not saved', 1)
    return w


# ---------------------------------------------------------------------------
# 2. Google Sheets content calendar -> Preflight
# ---------------------------------------------------------------------------
SHEET_COLUMNS = 'Text | Channels | Publish At | Media URL | Link | Status | Preflight Post ID | Issues'


def sheets_calendar() -> Workflow:
    w = Workflow('Schedule social media posts from a Google Sheets calendar, checked before they go out', 'sheets')
    w.note(
        'Overview',
        '## Schedule posts from a Google Sheets calendar, checked before they go out\n\n'
        'For teams that plan social posts in a spreadsheet and want to hear about a too-long caption or a '
        'wrong-shaped video when the row is marked ready, not when it fails at night.\n\n'
        '### How it works\n'
        '1. Every 15 minutes it reads rows whose **Status** is `Ready`.\n'
        '2. A **Media URL** is uploaded to Preflight first, which measures the file.\n'
        '3. Preflight checks text, link and media against the rules of every channel in the row.\n'
        '4. Rows that pass are scheduled for **Publish At**, or queued when it is empty, and get `Scheduled` and '
        'the post ID.\n'
        '5. Rows that fail get `Needs fix` and the reason, e.g. "Text is 385 characters; Bluesky allows 300."\n\n'
        '### Setup\n'
        f"1. {REQUIREMENTS.replace('n8n 2.43', 'n8n Cloud 2.45')}\n"
        f'2. {API_KEY} with the scopes `posts:read`, `posts:write`, `posts:publish`, `media:read` and '
        '`media:write`. Add it as a **Preflight API** credential in the four Preflight nodes.\n'
        f'3. Make a sheet with a tab named `Posts` and this header row:\n`{SHEET_COLUMNS}`\n'
        '4. In **Configuration**, paste the sheet\'s URL. Add a Google Sheets credential to the four Sheets nodes.\n\n'
        '### Customization\n'
        '- **Channels**: `bluesky, linkedin`, or `platform:channelId` for two accounts on one network. Empty uses '
        '**defaultChannels**.\n'
        '- **Publish At** (`2026-11-02 09:30`) uses the workflow\'s time zone, set under Workflow settings.',
        -800, -420, 600, 960, YELLOW,
    )
    w.note('Section: read rows', '### 1. The sheet is the source of truth\nOnly `Ready` rows run, so people can keep '
           'drafting in the same tab. Everything the workflow decides is written back here.',
           -60, -160, 720, 360)
    w.note('Section: media', '### 2. Measure the file first\nRules depend on the real file: length, frame rate, '
           'aspect ratio, size. A file that cannot be fetched marks only its own row `Error`.',
           700, -280, 680, 480)
    w.note('Section: check and schedule', '### 3. Check, then schedule or queue\nA refused row never reaches the '
           'scheduler. The idempotency key is the row and a hash of its text, so overlapping runs cannot make two posts.',
           1400, -440, 1440, 620)
    w.note('Section: write back', '### 4. Nothing disappears quietly\nA refusal or an API error lands in **Issues**. '
           'Fix the row, set it to `Ready` again, and the next run picks it up.',
           1400, 220, 1440, 340)

    w.node('Every 15 minutes', 'n8n-nodes-base.scheduleTrigger',
           {'rule': {'interval': [{'field': 'minutes', 'minutesInterval': 15}]}}, 1.2, 0, 0)
    w.node('Configuration', 'n8n-nodes-base.set', fields('sheets', [
        ('sheetUrl', 'https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit', 'string'),
        ('defaultChannels', 'bluesky, mastodon', 'string'),
    ]), 3.4, 220, 0)
    document = {'__rl': True, 'value': f'={{{{ {CONFIG}.sheetUrl }}}}', 'mode': 'url'}
    tab = {'__rl': True, 'value': 'Posts', 'mode': 'name'}
    w.node('Rows marked Ready', 'n8n-nodes-base.googleSheets', {
        'documentId': document, 'sheetName': tab,
        'filtersUI': {'values': [{'lookupColumn': 'Status', 'lookupValue': 'Ready'}]},
        # A date cell as text depends on the sheet's locale; its serial number does not.
        'options': {'outputFormatting': {'values': {'general': 'UNFORMATTED_VALUE', 'date': 'SERIAL_NUMBER'}}},
    }, 4.7, 440, 0)
    w.node('Has a file?', 'n8n-nodes-base.if', if_not_empty("={{ $json['Media URL'] }}"), 2.2, 760, 0)
    w.node('Upload file to Preflight', PREFLIGHT, {
        'resource': 'media', 'operation': 'upload', 'source': 'url',
        'sourceUrl': "={{ $json['Media URL'] }}", 'kind': 'auto', 'waitUntilReady': True,
    }, 1, 940, -140, onError='continueRegularOutput')
    w.node('File uploaded?', 'n8n-nodes-base.if', SAVED, 2.2, 1120, -140)
    row = "$('Rows marked Ready').item.json"
    w.node('Post to check', 'n8n-nodes-base.set', fields('sheets-post', [
        ('row_number', f'={{{{ {row}.row_number }}}}', 'number'),
        ('text', f'={{{{ {row}.Text }}}}', 'string'),
        ('channels', f'={{{{ {row}.Channels || {CONFIG}.defaultChannels }}}}', 'string'),
        ('publishAt', f"={{{{ typeof {row}['Publish At'] === 'number' ? "
                      f"DateTime.fromMillis(Math.round(({row}['Publish At'] - 25569) * 86400000), {{ zone: 'utc' }})"
                      f".toFormat('yyyy-MM-dd HH:mm') : {row}['Publish At'] }}}}", 'string'),
        ('mediaId', "={{ $json.kind ? $json.id : '' }}", 'string'),
        ('link', f'={{{{ {row}.Link }}}}', 'string'),
    ]), 3.4, 1220, 0)
    post = "$('Post to check').item.json"
    post_fields = {
        'channels': f'={{{{ {post}.channels }}}}',
        'content': f'={{{{ {post}.text }}}}',
        'additionalFields': {'mediaIds': f'={{{{ {post}.mediaId }}}}', 'linkUrl': f'={{{{ {post}.link }}}}'},
    }
    key = f"={{{{ 'sheet-' + {post}.row_number + '-' + {post}.text.hash('sha256') }}}}"
    w.node('Check against network rules', PREFLIGHT,
           {'resource': 'post', 'operation': 'validate', **post_fields}, 1, 1460, 0, **RETRY)
    w.node('Passes every network?', 'n8n-nodes-base.if', if_ok(), 2.2, 1680, 0)
    w.node('Has a time?', 'n8n-nodes-base.if', if_not_empty(f'={{{{ {post}.publishAt }}}}'), 2.2, 1900, -200)
    w.node('Schedule in Preflight', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **post_fields,
        'when': 'scheduled', 'scheduledAt': f'={{{{ {post}.publishAt }}}}', 'idempotencyKey': key,
    }, 1, 2140, -320, onError='continueRegularOutput')
    w.node('Queue in Preflight', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **post_fields,
        'when': 'queue', 'idempotencyKey': key,
    }, 1, 2140, -120, onError='continueRegularOutput')
    w.node('Made the post?', 'n8n-nodes-base.if', SAVED, 2.2, 2380, -200)

    def update(status, extra):
        return {
            'operation': 'update', 'documentId': document, 'sheetName': tab,
            'columns': {
                'mappingMode': 'defineBelow',
                'value': {'row_number': f'={{{{ {row}.row_number }}}}', 'Status': status, **extra},
                'matchingColumns': ['row_number'],
                'schema': [
                    {'id': column, 'displayName': column, 'required': False, 'defaultMatch': False,
                     'display': True, 'type': 'string', 'canBeUsedToMatch': True}
                    for column in ['row_number', 'Status', 'Preflight Post ID', 'Issues']
                ],
            },
            'options': {},
        }

    w.node('Mark Scheduled', 'n8n-nodes-base.googleSheets',
           update('Scheduled', {'Preflight Post ID': '={{ $json.id }}', 'Issues': ''}), 4.7, 2620, -300)
    w.node('Mark Needs fix', 'n8n-nodes-base.googleSheets',
           update('Needs fix', {'Issues': ISSUES}), 4.7, 1900, 360)
    w.node('Mark Error', 'n8n-nodes-base.googleSheets',
           update('Error', {'Issues': ERROR_TEXT}), 4.7, 2620, 360)

    w.chain('Every 15 minutes', 'Configuration', 'Rows marked Ready', 'Has a file?')
    w.link('Has a file?', 'Upload file to Preflight', 0)
    w.link('Has a file?', 'Post to check', 1)
    w.link('Upload file to Preflight', 'File uploaded?')
    w.link('File uploaded?', 'Post to check', 0)
    w.link('File uploaded?', 'Mark Error', 1)
    w.chain('Post to check', 'Check against network rules', 'Passes every network?')
    w.link('Passes every network?', 'Has a time?', 0)
    w.link('Passes every network?', 'Mark Needs fix', 1)
    w.link('Has a time?', 'Schedule in Preflight', 0)
    w.link('Has a time?', 'Queue in Preflight', 1)
    w.link('Schedule in Preflight', 'Made the post?')
    w.link('Queue in Preflight', 'Made the post?')
    w.link('Made the post?', 'Mark Scheduled', 0)
    w.link('Made the post?', 'Mark Error', 1)
    return w


# ---------------------------------------------------------------------------
# 3. One vertical video -> YouTube Shorts, Instagram Reels, TikTok
# ---------------------------------------------------------------------------
def video_to_shorts() -> Workflow:
    w = Workflow('Queue one vertical video to YouTube Shorts, Instagram Reels and TikTok after a rules check', 'shorts')
    w.note(
        'Overview',
        '## One vertical video to Shorts, Reels and TikTok\n\n'
        'For creators and social teams who post the same short video on three networks and want it checked '
        'against all three before anything is uploaded to them.\n\n'
        '### How it works\n'
        '1. You upload a video, a caption and a YouTube title through an n8n form.\n'
        '2. The video goes to Preflight, which measures it: length, size, frame rate, aspect ratio.\n'
        '3. Preflight checks the video and caption against YouTube Shorts, Instagram Reels and TikTok rules.\n'
        '4. If all three accept it, it is queued for each channel\'s next free slot. The form shows the result, '
        'or the exact reasons it was refused.\n\n'
        '### Setup\n'
        f'1. {REQUIREMENTS}\n'
        f'2. {API_KEY} with the scopes `posts:read`, `posts:write`, `posts:publish`, `media:read` and '
        '`media:write`. Add it as a **Preflight API** credential in the three Preflight nodes.\n'
        '3. Add a Basic Auth credential to **Upload form**, so only people with the login can queue videos.\n'
        '4. In **Configuration**, list the channels, e.g. `youtube, instagram, tiktok`.\n\n'
        '### Customization\n'
        '- TikTok goes to the creator\'s inbox as **Only me** to finish in the app. Change the TikTok options in '
        'both Preflight post nodes when you are ready to post directly.\n'
        '- Swap the form for a Google Drive or Dropbox trigger. Cut clips yourself: downloading from YouTube is '
        'against its terms.',
        -800, -440, 600, 960, YELLOW,
    )
    w.note('Section: upload', '### 1. Form and upload\nThe video is uploaded in parts and measured before any '
           'network sees it.',
           -60, -160, 740, 360)
    w.note('Section: check and queue', '### 2. Check all three networks, then queue\nThe idempotency key is the '
           'media ID, so submitting twice does not queue twice.',
           700, -320, 1180, 620)

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
    }, 2.2, 0, 0, webhookId=nid('shorts-form'))
    w.node('Configuration', 'n8n-nodes-base.set', fields('shorts', [
        ('channels', 'youtube, instagram, tiktok', 'string'),
    ], include_other=True), 3.4, 220, 0)
    w.node('Upload video to Preflight', PREFLIGHT, {
        'resource': 'media', 'operation': 'upload', 'source': 'binary',
        'binaryPropertyName': 'Video', 'kind': 'video', 'waitUntilReady': True,
        'options': {'waitTimeout': 900},
    }, 1, 440, 0)
    form = "$('Upload form').item.json"
    video = "$('Upload video to Preflight').item.json.id"
    post_fields = {
        'channels': f'={{{{ {CONFIG}.channels }}}}',
        'content': f'={{{{ {form}.Caption }}}}',
        'additionalFields': {'mediaIds': f'={{{{ {video} }}}}'},
        'networkOptions': {
            'youtubeTitle': f"={{{{ {form}['YouTube title'] }}}}",
            'youtubeShort': True,
            'youtubePrivacy': 'public',
            'instagramPlacement': 'reel',
            'tiktokPrivacy': 'SELF_ONLY',
            'tiktokAsDraft': True,
        },
    }
    w.node('Check video rules', PREFLIGHT,
           {'resource': 'post', 'operation': 'validate', **post_fields}, 1, 760, 0, **RETRY)
    w.node('Passes every network?', 'n8n-nodes-base.if', if_ok(), 2.2, 980, 0)
    w.node('Queue on every channel', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **post_fields,
        'when': 'queue',
        'idempotencyKey': f"={{{{ 'short-' + {video} }}}}",
    }, 1, 1200, -120, onError='continueRegularOutput')
    w.node('Queued?', 'n8n-nodes-base.if', SAVED, 2.2, 1420, -120)
    w.node('Queued', 'n8n-nodes-base.form', {
        'operation': 'completion',
        'completionTitle': 'Queued',
        'completionMessage': '=It goes out on each channel at its next free slot. Preflight post {{ $json.id }}.',
        'options': {},
    }, 1, 1660, -220, webhookId=nid('shorts-done'))
    w.node('Not queued', 'n8n-nodes-base.form', {
        'operation': 'completion',
        'completionTitle': 'Not queued',
        'completionMessage': ERROR_TEXT,
        'options': {},
    }, 1, 1660, -20, webhookId=nid('shorts-error'))
    w.node('Refused', 'n8n-nodes-base.form', {
        'operation': 'completion',
        'completionTitle': 'Not queued: fix this first',
        'completionMessage': ISSUES,
        'options': {},
    }, 1, 1200, 140, webhookId=nid('shorts-refused'))

    w.chain('Upload form', 'Configuration', 'Upload video to Preflight', 'Check video rules', 'Passes every network?')
    w.link('Passes every network?', 'Queue on every channel', 0)
    w.link('Passes every network?', 'Refused', 1)
    w.link('Queue on every channel', 'Queued?')
    w.link('Queued?', 'Queued', 0)
    w.link('Queued?', 'Not queued', 1)
    return w


# ---------------------------------------------------------------------------
# 4. Notion database -> Preflight (kept in the repo; not sent to the gallery,
#    which refuses near-copies of another template)
# ---------------------------------------------------------------------------
def notion_calendar() -> Workflow:
    w = Workflow('Schedule social media posts from a Notion database, checked before they go out', 'notion')
    w.note(
        'Overview',
        '## Schedule posts from a Notion content database\n\n'
        'The Google Sheets calendar template, for teams that plan in Notion.\n\n'
        '### How it works\n'
        '1. Every 15 minutes, pages with **Status** `Ready` are read.\n'
        '2. A **Media URL** is uploaded to Preflight first.\n'
        '3. Preflight checks each post against every channel\'s rules.\n'
        '4. Pages that pass are scheduled for **Publish At** and get `Scheduled` and the post ID; the rest get '
        '`Needs fix` and the reason.\n\n'
        '### Setup\n'
        f'1. {REQUIREMENTS}\n'
        f'2. {API_KEY} with the scopes `posts:read`, `posts:write`, `posts:publish`, `media:read` and '
        '`media:write`, and add it as a **Preflight API** credential.\n'
        '3. Give the database these properties: `Name` (title), `Text` (text), `Channels` (text), '
        '`Publish At` (date with time), `Media URL` (URL), `Status` (status: Ready, Scheduled, Needs fix), '
        '`Preflight ID` (text), `Issues` (text).\n'
        '4. Pick the database in **Pages marked Ready** and add a Notion credential to the Notion nodes.\n\n'
        '### Customization\n'
        '- Empty **Channels** uses **defaultChannels** from Configuration.',
        -800, -420, 600, 860, YELLOW,
    )
    w.node('Every 15 minutes', 'n8n-nodes-base.scheduleTrigger',
           {'rule': {'interval': [{'field': 'minutes', 'minutesInterval': 15}]}}, 1.2, 0, 0)
    w.node('Configuration', 'n8n-nodes-base.set', fields('notion', [
        ('defaultChannels', 'bluesky, mastodon', 'string'),
    ]), 3.4, 220, 0)
    w.node('Pages marked Ready', 'n8n-nodes-base.notion', {
        'resource': 'databasePage', 'operation': 'getAll',
        'databaseId': {'__rl': True, 'value': '', 'mode': 'list'}, 'returnAll': True,
        'filterType': 'manual',
        'filters': {'conditions': [{'key': 'Status|status', 'condition': 'equals', 'statusValue': 'Ready'}]},
        'options': {},
    }, 2.2, 440, 0)
    w.node('Has a file?', 'n8n-nodes-base.if', if_not_empty('={{ $json.property_media_url }}'), 2.2, 660, 0)
    w.node('Upload file to Preflight', PREFLIGHT, {
        'resource': 'media', 'operation': 'upload', 'source': 'url',
        'sourceUrl': '={{ $json.property_media_url }}', 'kind': 'auto', 'waitUntilReady': True,
    }, 1, 880, -120)
    page = "$('Pages marked Ready').item.json"
    w.node('Post to check', 'n8n-nodes-base.set', fields('notion-post', [
        ('pageId', f'={{{{ {page}.id }}}}', 'string'),
        ('text', f'={{{{ {page}.property_text }}}}', 'string'),
        ('channels', f'={{{{ {page}.property_channels || {CONFIG}.defaultChannels }}}}', 'string'),
        ('publishAt', f'={{{{ {page}.property_publish_at?.start }}}}', 'string'),
        ('mediaId', "={{ $json.kind ? $json.id : '' }}", 'string'),
    ]), 3.4, 1100, 0)
    post = "$('Post to check').item.json"
    post_fields = {
        'channels': f'={{{{ {post}.channels }}}}',
        'content': f'={{{{ {post}.text }}}}',
        'additionalFields': {'mediaIds': f'={{{{ {post}.mediaId }}}}'},
    }
    w.node('Check against network rules', PREFLIGHT,
           {'resource': 'post', 'operation': 'validate', **post_fields}, 1, 1320, 0, **RETRY)
    w.node('Passes every network?', 'n8n-nodes-base.if', if_ok(), 2.2, 1540, 0)
    w.node('Schedule in Preflight', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **post_fields,
        'when': 'scheduled', 'scheduledAt': f'={{{{ {post}.publishAt }}}}',
        'idempotencyKey': f"={{{{ 'notion-' + {post}.pageId + '-' + {post}.text.hash('sha256') }}}}",
    }, 1, 1760, -100, **RETRY)

    def status(value, extra):
        return {
            'resource': 'databasePage', 'operation': 'update',
            'pageId': {'__rl': True, 'value': f'={{{{ {post}.pageId }}}}', 'mode': 'id'},
            'propertiesUi': {'propertyValues': [{'key': 'Status|status', 'statusValue': value}, *extra]},
            'options': {},
        }

    w.node('Mark Scheduled', 'n8n-nodes-base.notion', status('Scheduled', [
        {'key': 'Preflight ID|rich_text', 'textContent': '={{ $json.id }}'},
    ]), 2.2, 1980, -100)
    w.node('Mark Needs fix', 'n8n-nodes-base.notion', status('Needs fix', [
        {'key': 'Issues|rich_text', 'textContent': ISSUES},
    ]), 2.2, 1760, 120)
    w.chain('Every 15 minutes', 'Configuration', 'Pages marked Ready', 'Has a file?')
    w.link('Has a file?', 'Upload file to Preflight', 0)
    w.link('Has a file?', 'Post to check', 1)
    w.link('Upload file to Preflight', 'Post to check')
    w.chain('Post to check', 'Check against network rules', 'Passes every network?')
    w.link('Passes every network?', 'Schedule in Preflight', 0)
    w.link('Passes every network?', 'Mark Needs fix', 1)
    w.link('Schedule in Preflight', 'Mark Scheduled')
    return w


# ---------------------------------------------------------------------------
# 5. post.failed -> Slack alert
# ---------------------------------------------------------------------------
def failed_alerts() -> Workflow:
    w = Workflow('Get a Slack alert when a scheduled social media post fails to publish', 'alerts')
    w.note(
        'Overview',
        '## Slack alert when a social media post fails\n\n'
        'For anyone who schedules posts in Preflight and wants to hear about a failure the moment it '
        'happens, not when a client asks why the post is missing.\n\n'
        '### How it works\n'
        '1. Preflight sends `post.failed` once it has stopped retrying a channel, so this runs once per real '
        'failure, not on every attempt.\n'
        '2. The workflow reads the post so the alert can quote its text.\n'
        '3. Slack gets the network, the reason in plain words, whether a retry can work, and a link to the post.\n\n'
        '### Setup\n'
        f'1. {REQUIREMENTS}\n'
        f'2. {API_KEY} with the scopes `posts:read`, `webhooks:read` and `webhooks:write`. Add it as a '
        '**Preflight API** credential in both Preflight nodes.\n'
        '3. Add a Slack credential and set the channel in **Configuration**.\n'
        '4. Activate the workflow. That registers the webhook in Preflight; deactivating removes it. '
        'Preflight only delivers to a public https URL, so a local n8n needs a tunnel.\n\n'
        '### Customization\n'
        '- Add `post.published` to the trigger to log every live post too.\n'
        '- Swap Slack for Telegram, Discord or e-mail: everything they need is in **Write alert**.',
        -800, -400, 600, 840, YELLOW,
    )
    w.note('Section: alert', '### Failure → Slack\nEvery delivery is signed; the trigger refuses anything '
           'unsigned, changed or older than five minutes.',
           -60, -160, 1180, 380)

    w.node('When a post fails', PREFLIGHT_TRIGGER, {'events': ['post.failed']},
           1, 0, 0, webhookId=nid('alerts-trigger'))
    w.node('Configuration', 'n8n-nodes-base.set', fields('alerts', [
        ('slackChannel', '#social-alerts', 'string'),
    ]), 3.4, 220, 0)
    w.node('Get the post', PREFLIGHT, {
        'resource': 'post', 'operation': 'get', 'postId': "={{ $('When a post fails').item.json.postId }}",
    }, 1, 440, 0, onError='continueRegularOutput')
    event = "$('When a post fails').item.json"
    msg = (
        f"={{{{ ':warning: Preflight: post failed on ' + {event}.platform + '\\n' + "
        f"'Why: ' + {event}.error + '\\n' + "
        f"({event}.permanent ? 'Retrying will not help until this is fixed.' : 'A retry may work.') + '\\n' + "
        "'Text: ' + ($json.content || '(could not read the post)').slice(0, 140) + '\\n' + "
        f"'Open: https://preflight.social/posts?post=' + {event}.postId }}}}"
    )
    w.node('Write alert', 'n8n-nodes-base.set', fields('alerts-msg', [('message', msg, 'string')]), 3.4, 660, 0)
    w.node('Send to Slack', 'n8n-nodes-base.slack', {
        'select': 'channel',
        'channelId': {'__rl': True, 'value': f'={{{{ {CONFIG}.slackChannel }}}}', 'mode': 'name'},
        'text': '={{ $json.message }}',
        'otherOptions': {'includeLinkToWorkflow': False},
    }, 2.3, 880, 0, webhookId=nid('alerts-slack'), **RETRY)
    w.chain('When a post fails', 'Configuration', 'Get the post', 'Write alert', 'Send to Slack')
    return w


# ---------------------------------------------------------------------------
# 6. Telegram idea -> AI video (Kling on fal.ai) -> checked twice -> approve -> queue
# ---------------------------------------------------------------------------
TELEGRAM = 'n8n-nodes-base.telegram'
FAL = {'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth'}


def telegram_text(name, js, x, y):
    # Sent as HTML with the text escaped: the node's default, legacy Markdown, refuses any
    # message with an unpaired underscore, and error messages are full of them.
    return dict(name=name, type_=TELEGRAM, params={
        'chatId': "={{ $('New idea in Telegram').first().json.message.chat.id }}",
        'text': '={{ String(' + js + ").replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }}",
        'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML'},
    }, version=1.2, x=x, y=y)


def add_telegram_text(w, name, text, x, y):
    # A reply that times out once should not end a run that may already have paid for a render.
    t = telegram_text(name, text, x, y)
    w.node(t['name'], t['type_'], t['params'], t['version'], t['x'], t['y'], **RETRY)


def ai_video_from_telegram() -> Workflow:
    w = Workflow('Turn a Telegram message into an AI short video, checked against each network before and after rendering', 'aivideo')
    w.note(
        'Overview',
        '## Telegram idea → AI short video → approved → queued\n\n'
        'For creators with ideas on the go: text one to your bot, get a vertical clip back, tap Approve, and it '
        'is queued for YouTube Shorts, Instagram Reels and TikTok.\n\n'
        '### How it works\n'
        '1. Claude turns an idea from your own chat into a video prompt, a caption and a YouTube title.\n'
        '2. Before any money is spent, Preflight checks the caption and planned clip against each channel\'s '
        'rules. A refusal comes back with the reason.\n'
        '3. Kling renders the clip on fal.ai (up to about ten minutes).\n'
        '4. Preflight measures the real file and checks it again.\n'
        '5. The bot sends the clip with Approve and Skip. Approve queues it for each channel\'s next free slot.\n\n'
        '### Setup\n'
        f"1. {REQUIREMENTS.replace('n8n 2.43', 'self-hosted n8n 2.43')}\n"
        f'2. {API_KEY} with the scopes `posts:read`, `posts:write`, `posts:publish`, `media:read` and '
        '`media:write`. Add it as a **Preflight API** credential.\n'
        '3. Create a bot with @BotFather and add its token as a Telegram credential.\n'
        '4. Add an Anthropic credential to **Claude**, and your fal.ai key as Header Auth (`Authorization`: '
        '`Key YOUR_FAL_KEY`).\n'
        '5. In **Configuration**, set your channels and chat ID (message the bot once: it is `message.chat.id` '
        'in the trigger\'s output).\n\n'
        '### Customization\n'
        '- Each clip costs money on fal.ai: Kling 2.6 Pro is $0.07 per second, $0.14 with **withSound** on. '
        'Kling takes 5 or 10 **seconds**. For another model change **falModel** and **Start the render**.\n'
        '- TikTok goes to the inbox as **Only me** until you change the TikTok options.',
        -800, -460, 600, 1040, YELLOW,
    )
    w.note('Section: idea', '### 1. Your idea, from your chat only\nAnyone can message a bot. Messages from other chats '
           'are ignored, so nobody else can spend your render credits.', -60, -200, 960, 400)
    w.note('Section: plan', '### 2. Plan, then check for free\nThe caption and the planned clip are checked before '
           'rendering, so a post a network would refuse never costs a render.', 940, -200, 1080, 560)
    w.note('Section: render', '### 3. Render and wait\nfal.ai queues the job. The loop checks every 20 seconds and '
           'gives up after about ten minutes.', 2060, -200, 1060, 640)
    w.note('Section: check file', '### 4. Check the real file\nLength, frame rate, aspect ratio and size come from the '
           'file itself, not from what was asked for.', 3140, -200, 1040, 560)
    w.note('Section: approve', '### 5. You approve, then it is queued\nThe idempotency key is the file, so approving '
           'twice never makes two posts. Skip leaves nothing behind but the file in Preflight.',
           4220, -320, 1380, 720)

    w.node('New idea in Telegram', 'n8n-nodes-base.telegramTrigger',
           {'updates': ['message'], 'additionalFields': {}}, 1.2, 0, 0, webhookId=nid('aivideo-trigger'))
    w.node('Configuration', 'n8n-nodes-base.set', fields('aivideo', [
        ('allowedChatId', 'YOUR_CHAT_ID', 'string'),
        ('channels', 'youtube, instagram, tiktok', 'string'),
        ('falModel', 'fal-ai/kling-video/v2.6/pro/text-to-video', 'string'),
        ('seconds', 5, 'number'),
        ('withSound', False, 'boolean'),
    ]), 3.4, 220, 0)
    msg = "$('New idea in Telegram').first().json.message"
    w.node('From your chat?', 'n8n-nodes-base.if', {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 2},
            'conditions': [
                {'id': nid('aivideo-chat'), 'leftValue': f'={{{{ String({msg}.chat.id) }}}}',
                 'rightValue': f'={{{{ String({CONFIG}.allowedChatId) }}}}',
                 'operator': {'type': 'string', 'operation': 'equals'}},
                {'id': nid('aivideo-text'), 'leftValue': f'={{{{ {msg}.text }}}}', 'rightValue': '',
                 'operator': {'type': 'string', 'operation': 'notEmpty', 'singleValue': True}},
            ],
            'combinator': 'and',
        },
        'looseTypeValidation': True,
        'options': {},
    }, 2.2, 440, 0)
    add_telegram_text(w, 'Say it has started', "'Planning a video for: ' + " + msg + '.text.slice(0, 200)', 660, 0)

    w.node('Plan the video', '@n8n/n8n-nodes-langchain.chainLlm', {
        'promptType': 'define',
        'text': '=Plan a vertical short video (9:16) of about {{ ' + CONFIG + '.seconds }} seconds from this idea, '
                'for YouTube Shorts, Instagram Reels and TikTok.\n\nIdea: {{ ' + msg + '.text }}\n\n'
                'videoPrompt: one paragraph for a text-to-video model: subject, action, setting, camera, light. '
                'No text on screen, no logos, no real people.\n'
                'caption: under 150 characters, plain text, at most three hashtags, no links.\n'
                'youtubeTitle: under 70 characters.',
        'hasOutputParser': True,
    }, 1.7, 980, 0)
    w.node('Claude', '@n8n/n8n-nodes-langchain.lmChatAnthropic', {
        'model': {'__rl': True, 'value': 'claude-haiku-4-5', 'mode': 'list', 'cachedResultName': 'Claude Haiku 4.5'},
        'options': {},
    }, 1.6, 980, 220)
    w.node('Plan format', '@n8n/n8n-nodes-langchain.outputParserStructured', {
        'schemaType': 'fromJson',
        'jsonSchemaExample': json.dumps({'videoPrompt': 'A ceramic cup on a sunlit kitchen table…',
                                         'caption': 'Morning ritual #coffee', 'youtubeTitle': 'Morning coffee in 5 seconds'}, indent=1),
    }, 1.3, 1140, 220)
    plan = "$('Plan the video').item.json.output"
    platforms = f"{CONFIG}.channels.split(',').map(c => c.trim().split(':')[0].toLowerCase()).filter(Boolean)"
    w.node('Check the plan', 'n8n-nodes-base.httpRequest', {
        'method': 'POST',
        'url': 'https://preflight.social/v1/platforms/check',
        'sendBody': True, 'specifyBody': 'json',
        'jsonBody': f"={{{{ JSON.stringify({{ text: {plan}.caption, platforms: {platforms}, "
                    f"media: [{{ kind: 'video', durationSeconds: Number({CONFIG}.seconds), fps: 24, width: 1080, height: 1920 }}] }}) }}}}",
        'options': {},
    }, 4.2, 1380, 0, **RETRY)
    w.node('Plan passes?', 'n8n-nodes-base.if', if_ok(), 2.2, 1600, 0)
    add_telegram_text(w, 'Tell the plan was refused', "'Not rendered, so nothing was spent. Preflight says:\\n' + " + ISSUES_JS, 1820, 200)

    w.node('Start the render', 'n8n-nodes-base.httpRequest', {
        'method': 'POST',
        'url': f'={{{{ "https://queue.fal.run/" + {CONFIG}.falModel }}}}',
        **FAL,
        'sendBody': True, 'specifyBody': 'json',
        'jsonBody': f"={{{{ JSON.stringify({{ prompt: {plan}.videoPrompt, duration: String({CONFIG}.seconds), "
                    f"aspect_ratio: '9:16', generate_audio: {CONFIG}.withSound === true }}) }}}}",
        'options': {},
    }, 4.2, 2120, 0)
    w.node('Wait 20 seconds', 'n8n-nodes-base.wait', {'amount': 20, 'unit': 'seconds'}, 1.1, 2340, 0,
           webhookId=nid('aivideo-wait'))
    job = "$('Start the render').first().json"
    w.node('Ask fal.ai for the status', 'n8n-nodes-base.httpRequest', {
        'url': f'={{{{ {job}.status_url }}}}', **FAL, 'options': {},
    }, 4.2, 2560, 0, **RETRY)
    finished = condition('={{ $json.status }}', {'type': 'string', 'operation': 'equals'})
    finished['conditions']['conditions'][0]['rightValue'] = 'COMPLETED'
    w.node('Finished?', 'n8n-nodes-base.if', finished, 2.2, 2780, 0)
    # $runIndex counts this node's runs: 30 rounds of 20 seconds is about ten minutes.
    keep = condition('={{ $runIndex }}', {'type': 'number', 'operation': 'lt'})
    keep['conditions']['conditions'][0]['rightValue'] = 30
    w.node('Keep waiting?', 'n8n-nodes-base.if', keep, 2.2, 2780, 240)
    add_telegram_text(w, 'Tell it took too long', f"'The render was still not finished after ten minutes. fal.ai request: ' + {job}.request_id", 3000, 340)
    w.node('Get the video', 'n8n-nodes-base.httpRequest', {
        'url': f'={{{{ {job}.response_url }}}}', **FAL, 'options': {},
    }, 4.2, 3000, 0, onError='continueRegularOutput')

    w.node('Got a video?', 'n8n-nodes-base.if', if_not_empty('={{ $json.video?.url }}'), 2.2, 3180, 0)
    add_telegram_text(w, 'Tell there is no video',
                      "'fal.ai returned no video: ' + ($json.detail ? JSON.stringify($json.detail) : $json.error || 'no reason given')",
                      3180, 220)
    w.node('Upload to Preflight', PREFLIGHT, {
        'resource': 'media', 'operation': 'upload', 'source': 'url',
        'sourceUrl': '={{ $json.video.url }}', 'kind': 'video', 'waitUntilReady': True,
    }, 1, 3360, 0, onError='continueRegularOutput')
    w.node('Uploaded?', 'n8n-nodes-base.if', SAVED, 2.2, 3560, 0)
    add_telegram_text(w, 'Tell the upload failed', ERR_JS.replace("'Preflight refused the post'", "'Preflight could not take the file'"), 3760, 200)
    video = "$('Upload to Preflight').item.json.id"
    post_fields = {
        'channels': f'={{{{ {CONFIG}.channels }}}}',
        'content': f'={{{{ {plan}.caption }}}}',
        'additionalFields': {'mediaIds': f'={{{{ {video} }}}}'},
        'networkOptions': {
            'youtubeTitle': f'={{{{ {plan}.youtubeTitle }}}}',
            'youtubeShort': True,
            'youtubePrivacy': 'public',
            'instagramPlacement': 'reel',
            'tiktokPrivacy': 'SELF_ONLY',
            'tiktokAsDraft': True,
        },
    }
    w.node('Check the video', PREFLIGHT, {'resource': 'post', 'operation': 'validate', **post_fields},
           1, 3760, 0, **RETRY)
    w.node('Video passes?', 'n8n-nodes-base.if', if_ok(), 2.2, 3980, 0)
    add_telegram_text(w, 'Tell the video was refused', "'The clip was rendered but would be refused:\\n' + " + ISSUES_JS, 4000, 240)

    w.node('Send the clip', TELEGRAM, {
        'operation': 'sendVideo',
        'chatId': f"={{{{ {msg}.chat.id }}}}",
        'file': "={{ $('Get the video').first().json.video.url }}",
        'additionalFields': {'caption': f'={{{{ {plan}.caption }}}}'},
    }, 1.2, 4300, -100, **RETRY)
    w.node('Approve or skip', TELEGRAM, {
        'operation': 'sendAndWait',
        'chatId': f"={{{{ {msg}.chat.id }}}}",
        # This message is always sent as legacy Markdown, so its text is escaped for it.
        'message': f"={{{{ ('Queue this clip for ' + {CONFIG}.channels + '?\\nYouTube title: ' + {plan}.youtubeTitle)"
                   ".replace(/([_*`\\[])/g, '\\\\$1') }}}}",
        'approvalOptions': {'values': {'approvalType': 'double', 'approveLabel': 'Queue it', 'disapproveLabel': 'Skip'}},
        'options': {'limitWaitTime': {'values': {'limitType': 'afterTimeInterval', 'resumeAmount': 24, 'resumeUnit': 'hours'}},
                    'appendAttribution': False},
    }, 1.2, 4520, -100, webhookId=nid('aivideo-approve'))
    w.node('Approved?', 'n8n-nodes-base.if', if_ok('={{ $json.data?.approved === true }}'), 2.2, 4740, -100)
    w.node('Queue on every channel', PREFLIGHT, {
        'resource': 'post', 'operation': 'create', **post_fields,
        'when': 'queue',
        'idempotencyKey': f"={{{{ 'tg-video-' + {video} }}}}",
    }, 1, 4960, -200, onError='continueRegularOutput')
    w.node('Queued?', 'n8n-nodes-base.if', SAVED, 2.2, 5180, -200)
    add_telegram_text(w, 'Tell it is queued', "'Queued.\\n' + $json.targets.map(t => t.platform + ': ' + (t.scheduledAt || $json.scheduledAt || 'next free slot')).join('\\n')", 5400, -280)
    add_telegram_text(w, 'Tell it was not queued', ERR_JS, 5400, -80)
    add_telegram_text(w, 'Tell it was skipped', "'Skipped. Nothing was posted.'", 4960, 100)

    w.chain('New idea in Telegram', 'Configuration', 'From your chat?')
    w.link('From your chat?', 'Say it has started', 0)
    w.chain('Say it has started', 'Plan the video', 'Check the plan', 'Plan passes?')
    w.link('Claude', 'Plan the video', kind='ai_languageModel')
    w.link('Plan format', 'Plan the video', kind='ai_outputParser')
    w.link('Plan passes?', 'Start the render', 0)
    w.link('Plan passes?', 'Tell the plan was refused', 1)
    w.chain('Start the render', 'Wait 20 seconds', 'Ask fal.ai for the status', 'Finished?')
    w.link('Finished?', 'Get the video', 0)
    w.link('Finished?', 'Keep waiting?', 1)
    w.link('Keep waiting?', 'Wait 20 seconds', 0)
    w.link('Keep waiting?', 'Tell it took too long', 1)
    w.chain('Get the video', 'Got a video?')
    w.link('Got a video?', 'Upload to Preflight', 0)
    w.link('Got a video?', 'Tell there is no video', 1)
    w.chain('Upload to Preflight', 'Uploaded?')
    w.link('Uploaded?', 'Check the video', 0)
    w.link('Uploaded?', 'Tell the upload failed', 1)
    w.chain('Check the video', 'Video passes?')
    w.link('Video passes?', 'Send the clip', 0)
    w.link('Video passes?', 'Tell the video was refused', 1)
    w.chain('Send the clip', 'Approve or skip', 'Approved?')
    w.link('Approved?', 'Queue on every channel', 0)
    w.link('Approved?', 'Tell it was skipped', 1)
    w.chain('Queue on every channel', 'Queued?')
    w.link('Queued?', 'Tell it is queued', 0)
    w.link('Queued?', 'Tell it was not queued', 1)
    return w


TEMPLATES = [
    ('01-rss-ai-caption-validate-draft', rss_to_drafts),
    ('02-google-sheets-content-calendar', sheets_calendar),
    ('03-vertical-video-shorts-reels-tiktok', video_to_shorts),
    ('04-notion-database-to-preflight', notion_calendar),
    ('05-failed-post-slack-alert', failed_alerts),
    ('06-telegram-ai-video-kling', ai_video_from_telegram),
]


def drafts_only(w: Workflow) -> Workflow:
    for node in w.nodes:
        p = node['parameters']
        if node['type'] == PREFLIGHT and p.get('operation') == 'create':
            p['when'] = 'draft'
            p.pop('scheduledAt', None)
    w.name = 'DRAFTS ' + w.name
    return w


def main():
    drafts_dir = None
    if '--drafts' in sys.argv:
        drafts_dir = Path(sys.argv[sys.argv.index('--drafts') + 1])
        drafts_dir.mkdir(parents=True, exist_ok=True)
    for slug, build in TEMPLATES:
        (HERE / f'{slug}.json').write_text(json.dumps(build().json(), indent=2, ensure_ascii=False) + '\n')
        if drafts_dir:
            (drafts_dir / f'{slug}.json').write_text(json.dumps(drafts_only(build()).json(), indent=2, ensure_ascii=False))
    print('written', len(TEMPLATES))


if __name__ == '__main__':
    main()
