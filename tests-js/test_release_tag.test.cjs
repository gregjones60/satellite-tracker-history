const {test} = require('node:test');
const assert = require('node:assert/strict');
const checkReleaseTag = require('../.github/scripts/check-release-tag.cjs');

function setup({refError, commitError, sha='tested'}={}) {
  const calls=[], failures=[], messages=[];
  return {
    calls, failures, messages,
    args: {
      tag: 'v0.5.2', testedSha: 'tested',
      context: {repo: {owner: 'owner', repo: 'repo'}},
      core: {info: message=>messages.push(message), setFailed: message=>failures.push(message)},
      github: {rest: {
        git: {getRef: async args=>{
          calls.push(['ref', args]);
          if(refError) throw refError;
          return {data: {object: {type: 'tag', sha: 'annotated-tag-object'}}};
        }},
        repos: {getCommit: async args=>{
          calls.push(['commit', args]);
          if(commitError) throw commitError;
          return {data: {sha}};
        }},
      }},
    },
  };
}

test('missing tag permits a first release without requesting an absent commit', async ()=>{
  const s=setup({refError: Object.assign(new Error('Not Found'), {status:404})});
  await checkReleaseTag(s.args);
  assert.deepEqual(s.calls, [['ref', {owner:'owner', repo:'repo', ref:'tags/v0.5.2'}]]);
  assert.equal(s.failures.length, 0);
  assert.match(s.messages[0], /release will create it/);
});

test('existing annotated tag resolves to the tested commit', async ()=>{
  const s=setup();
  await checkReleaseTag(s.args);
  assert.deepEqual(s.calls[1], ['commit', {owner:'owner', repo:'repo', ref:'refs/tags/v0.5.2'}]);
  assert.equal(s.failures.length, 0);
});

test('existing tag at a different commit blocks release', async ()=>{
  const s=setup({sha:'other'});
  await checkReleaseTag(s.args);
  assert.equal(s.failures.length, 1);
  assert.match(s.failures[0], /Bump the manifest version/);
});

for(const status of [403, 422, 500]) {
  test(`reference lookup errors (${status}) are not treated as missing tags`, async ()=>{
    const error=Object.assign(new Error('API failure'), {status});
    const s=setup({refError:error});
    await assert.rejects(checkReleaseTag(s.args), err=>err===error);
    assert.equal(s.calls.length, 1);
  });
}

test('commit resolution errors propagate even when they are 404', async ()=>{
  const error=Object.assign(new Error('Commit failure'), {status:404});
  const s=setup({commitError:error});
  await assert.rejects(checkReleaseTag(s.args), err=>err===error);
});
