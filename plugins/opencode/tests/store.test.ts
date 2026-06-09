import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { deriveStorePath } from '../src/index.ts';

describe('deriveStorePath', () => {
  it('uses MEMOIR_STORE env var when set', () => {
    process.env.MEMOIR_STORE = '/tmp/test-memoir-store';
    assert.strictEqual(deriveStorePath('/some/project'), '/tmp/test-memoir-store');
    delete process.env.MEMOIR_STORE;
  });

  it('uses homedir slug from cwd when no env', () => {
    const result = deriveStorePath('/home/user/my-project');
    assert.match(result, /^\/.*\.memoir/);
    assert.ok(result.includes('my-project'));
  });

  it('replaces slashes and dots with hyphens in slug', () => {
    const result = deriveStorePath('/home/user/dev/my.app');
    assert.match(result, /my-app$/);
  });

  it('handles cwd at root', () => {
    const result = deriveStorePath('/');
    assert.match(result, /^\/.*\.memoir\/-$/);
  });

  it('handles cwd with hyphens and underscores', () => {
    const result = deriveStorePath('/home/user/my_project-v2');
    assert.ok(result.includes('my_project-v2'));
  });
});
