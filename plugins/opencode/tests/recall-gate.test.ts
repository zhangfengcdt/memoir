import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { isAcknowledgement, shouldTriggerRecall } from '../src/index.ts';

describe('isAcknowledgement', () => {
  it('recognises common word acknowledgements', () => {
    const acks = [
      'ok', 'thanks', 'thank you', 'sounds good', 'got it',
      'perfect', 'great', 'cool', 'nice', 'awesome',
      'understood', 'makes sense', 'agree', 'right',
      'sure', 'yes', 'no', 'done', 'nvm', 'never mind',
      'lgtm', 'looks good', 'proceed', 'continue', 'good', 'fine',
    ];
    for (const ack of acks) {
      assert.ok(isAcknowledgement(ack), `expected "${ack}" to be an acknowledgement`);
    }
  });

  it('allows up to 5 words starting with an ACK keyword', () => {
    // The function permits ≤5-word phrases that begin with an ACK word
    assert.ok(isAcknowledgement('ok lets try that approach'));   // 5 words, starts with ok
    assert.ok(isAcknowledgement('thanks for the help'));         // 4 words, starts with thanks
    assert.ok(isAcknowledgement('great thanks works now'));       // 4 words, starts with great
  });

  it('rejects text over 5 words', () => {
    assert.ok(!isAcknowledgement('ok that looks great thanks very much'));  // 7 words
    assert.ok(!isAcknowledgement('thanks for the help I really appreciate it'));  // 8 words
  });

  it('rejects empty text', () => {
    assert.ok(!isAcknowledgement(''));
  });

  it('is case-insensitive', () => {
    assert.ok(isAcknowledgement('OK'));
    assert.ok(isAcknowledgement('Thanks'));
    assert.ok(isAcknowledgement('Sounds Good'));
  });
});

describe('shouldTriggerRecall', () => {
  it('fires on explicit memoir commands regardless of length', () => {
    assert.ok(shouldTriggerRecall('memoir:recall'));
    assert.ok(shouldTriggerRecall('/recall'));
    assert.ok(shouldTriggerRecall('memoir:remember'));
    assert.ok(shouldTriggerRecall('/remember'));
    assert.ok(shouldTriggerRecall('use memoir-recall here'));
    assert.ok(shouldTriggerRecall('memoir-remember something'));
  });

  it('skips empty text', () => {
    assert.ok(!shouldTriggerRecall(''));
    assert.ok(!shouldTriggerRecall('   '));
  });

  it('skips very short text (< 10 chars)', () => {
    assert.ok(!shouldTriggerRecall('hi'));
    assert.ok(!shouldTriggerRecall('hello'));
    assert.ok(!shouldTriggerRecall('123456789'));
  });

  it('skips acknowledgements even if long enough', () => {
    assert.ok(!shouldTriggerRecall('ok'));
    assert.ok(!shouldTriggerRecall('thanks'));
    assert.ok(!shouldTriggerRecall('sounds good'));
  });

  it('fires on ≥40 chars with trigger patterns', () => {
    // Test the 39/40 boundary
    const thirtyNine = 'x'.repeat(39);
    assert.ok(!shouldTriggerRecall(thirtyNine), '39 chars should not fire');

    // ≥40 chars with various trigger patterns
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' implement the feature'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' fix this bug'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' refactor this module'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' ```code block``` '));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' def calculate()'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' remember to handle edge case'));
  });

  it('does not fire on ≥40 chars without trigger patterns', () => {
    assert.ok(!shouldTriggerRecall('x'.repeat(40) + ' the and or but for with'));
    assert.ok(!shouldTriggerRecall('x'.repeat(40) + ' going to the store today'));
  });

  it('fires on questions starting with wh-/how/should/can  (≥40 chars)', () => {
    // Question pattern requires text to START with the question word (^ anchor)
    assert.ok(shouldTriggerRecall('how does this caching layer work in production?'));
    assert.ok(shouldTriggerRecall('why is the build failing on the CI pipeline?'));
    assert.ok(shouldTriggerRecall('what is the best way to structure this module?'));
    assert.ok(shouldTriggerRecall('should I use dependency injection or a factory?'));
    assert.ok(shouldTriggerRecall('can you help me debug this race condition?'));
    assert.ok(shouldTriggerRecall('does it handle the edge cases correctly?'));
  });

  it('fires on ≥40 char code-related patterns', () => {
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' add error handling to payment'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' refactor the user module for DI'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' write tests for the API endpoint'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' design the schema for the feature'));
  });

  it('fires on file paths and extensions with ≥40 chars', () => {
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' check src/main.py'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' update the config.yaml values'));
    assert.ok(shouldTriggerRecall('x'.repeat(40) + ' refactor the main.py module'));
  });
});
