import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { coercePaths, tryPrettyJson, SECRET_PATTERN } from '../src/index.ts';

describe('coercePaths', () => {
  it('returns empty array for undefined', () => {
    assert.deepStrictEqual(coercePaths(undefined), []);
  });

  it('wraps a single string in array', () => {
    assert.deepStrictEqual(coercePaths('prefs.coding.style'), ['prefs.coding.style']);
  });

  it('filters falsy values from array', () => {
    assert.deepStrictEqual(coercePaths(['a', '', 'b', undefined as unknown as string, 'c']), ['a', 'b', 'c']);
  });

  it('passes through clean array', () => {
    assert.deepStrictEqual(coercePaths(['a', 'b', 'c']), ['a', 'b', 'c']);
  });
});

describe('tryPrettyJson', () => {
  it('pretty-prints valid JSON', () => {
    const result = tryPrettyJson('{"a":1,"b":{"c":2}}');
    assert.strictEqual(result, '{\n  "a": 1,\n  "b": {\n    "c": 2\n  }\n}');
  });

  it('passes non-JSON through unchanged', () => {
    const text = 'Memoir command failed (1): not found';
    assert.strictEqual(tryPrettyJson(text), text);
  });

  it('passes empty string through unchanged', () => {
    assert.strictEqual(tryPrettyJson(''), '');
  });

  it('handles array JSON', () => {
    const result = tryPrettyJson('[1, 2, 3]');
    assert.strictEqual(result, '[\n  1,\n  2,\n  3\n]');
  });
});

describe('SECRET_PATTERN', () => {
  it('matches API keys', () => {
    assert.ok(SECRET_PATTERN.test('api_key=sk-1234'));
    assert.ok(SECRET_PATTERN.test('apikey=abc123'));
    assert.ok(SECRET_PATTERN.test('api-key=xyz789'));
  });

  it('matches tokens', () => {
    assert.ok(SECRET_PATTERN.test('auth_token=ghp_xxx'));
    assert.ok(SECRET_PATTERN.test('token=eyJhbGci'));
  });

  it('matches passwords', () => {
    assert.ok(SECRET_PATTERN.test('password=hunter2'));
    assert.ok(SECRET_PATTERN.test('passwd=s3cret'));
  });

  it('matches private keys', () => {
    assert.ok(SECRET_PATTERN.test('-----BEGIN RSA PRIVATE KEY-----'));
    assert.ok(SECRET_PATTERN.test('-----BEGIN EC PRIVATE KEY-----'));
  });

  it('matches substrings of secret-related words (known limitation)', () => {
    // The pattern catches any text containing "secret", "token", "password"
    // even in innocent words like "secretary", "tokenization", "passwordless".
    // This is a best-effort heuristic; the plugin always warns before saving.
    assert.ok(SECRET_PATTERN.test('the secretary problem'));
    assert.ok(SECRET_PATTERN.test('tokenization of input'));
    assert.ok(SECRET_PATTERN.test('the passwordless approach'));
  });

  it('does not match clearly safe content', () => {
    assert.ok(!SECRET_PATTERN.test('use pytest for testing'));
    assert.ok(!SECRET_PATTERN.test('prefer functional components'));
    assert.ok(!SECRET_PATTERN.test('the API should return JSON'));
    assert.ok(!SECRET_PATTERN.test('database is PostgreSQL'));
  });
});
