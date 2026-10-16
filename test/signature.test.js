// Run after `npm run build`: node --test test/*.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createHmac } = require('node:crypto');
const { verifyPreflightSignature } = require('../dist/nodes/PreflightTrigger/PreflightTrigger.node.js');

// Signed the way Preflight's server signs deliveries (t=<unix>,v2=HMAC-SHA256 of "t.body").
const sign = (body, secret, t) => `t=${t},v2=${createHmac('sha256', secret).update(`${t}.${body}`).digest('hex')}`;
const secret = 'test-secret-for-unit-tests';
const body = JSON.stringify({ id: 'd1', event: 'post.failed', createdAt: '2026-10-16T15:50:00.000Z', data: { postId: 'p1' } });
const now = 1792166000;

test('a correctly signed, fresh delivery verifies', () => {
	assert.equal(verifyPreflightSignature(body, secret, sign(body, secret, now), now), true);
});

test('a changed body, another secret or a stale timestamp is refused', () => {
	assert.equal(verifyPreflightSignature(body.replace('p1', 'p2'), secret, sign(body, secret, now), now), false);
	assert.equal(verifyPreflightSignature(body, secret, sign(body, 'another-test-secret', now), now), false);
	assert.equal(verifyPreflightSignature(body, secret, sign(body, secret, now - 301), now), false);
	assert.equal(verifyPreflightSignature(body, secret, '', now), false);
	assert.equal(verifyPreflightSignature(body, secret, `t=${now},v2=00`, now), false);
});
