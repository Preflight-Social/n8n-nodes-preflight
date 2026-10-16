// Run after `npm run build`: node --test test/*.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { toUtcInstant } = require('../dist/nodes/Preflight/GenericFunctions.js');

test('wall-clock time is read in the workflow zone', () => {
	assert.equal(toUtcInstant('2026-11-02 09:30', 'Europe/Prague'), '2026-11-02T08:30:00.000Z');
	assert.equal(toUtcInstant('2026-07-02T09:30:00', 'Europe/Prague'), '2026-07-02T07:30:00.000Z');
	assert.equal(toUtcInstant('2026-11-02T09:30', 'America/New_York'), '2026-11-02T14:30:00.000Z');
});

test('a value with a zone keeps its instant', () => {
	assert.equal(toUtcInstant('2026-12-01T09:30:00.000+01:00', 'America/New_York'), '2026-12-01T08:30:00.000Z');
	assert.equal(toUtcInstant('2026-12-01T09:30:00Z', 'Europe/Prague'), '2026-12-01T09:30:00.000Z');
	assert.equal(toUtcInstant(new Date('2026-12-01T09:30:00Z'), 'Europe/Prague'), '2026-12-01T09:30:00.000Z');
	assert.equal(toUtcInstant({ toISO: () => '2026-12-01T10:30:00.000+01:00' }, 'UTC'), '2026-12-01T09:30:00.000Z');
});

test('daylight saving edges', () => {
	// Prague moves to summer time on 2027-03-28 at 02:00.
	assert.equal(toUtcInstant('2027-03-28 03:30', 'Europe/Prague'), '2027-03-28T01:30:00.000Z');
	assert.equal(toUtcInstant('2027-03-28 01:30', 'Europe/Prague'), '2027-03-28T00:30:00.000Z');
});

test('not a date', () => {
	assert.equal(toUtcInstant('', 'UTC'), undefined);
	assert.equal(toUtcInstant('next tuesday', 'UTC'), undefined);
	assert.equal(toUtcInstant(undefined, 'UTC'), undefined);
});
