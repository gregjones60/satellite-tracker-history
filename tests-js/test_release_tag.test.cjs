const {test} = require('node:test');
const assert = require('node:assert/strict');
const checkReleaseTag = require('../.github/scripts/check-release-tag.cjs');

function setup({refError, commitError, releaseExists=false, releaseError, sha='tested'}={}) {
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
        repos: {getReleaseByTag: async args=>{
          calls.push(['release', args]);
          if(releaseError)throw releaseError;
          if(releaseExists)return {data:{tag_name:args.tag}};
          throw Object.assign(new Error('No release'),{status:404});
        },getCommit: async args=>{
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
  assert.deepEqual(s.calls, [['release',{owner:'owner',repo:'repo',tag:'v0.5.2'}],['ref', {owner:'owner', repo:'repo', ref:'tags/v0.5.2'}]]);
  assert.equal(s.failures.length, 0);
  assert.match(s.messages[0], /release will create it/);
});

test('existing annotated tag resolves to the tested commit', async ()=>{
  const s=setup();
  await checkReleaseTag(s.args);
  assert.deepEqual(s.calls[2], ['commit', {owner:'owner', repo:'repo', ref:'refs/tags/v0.5.2'}]);
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
    assert.equal(s.calls.length, 2);
  });
}

test('commit resolution errors propagate even when they are 404', async ()=>{
  const error=Object.assign(new Error('Commit failure'), {status:404});
  const s=setup({commitError:error});
  await assert.rejects(checkReleaseTag(s.args), err=>err===error);
});


test('an existing release blocks version reuse even if its tag was deleted', async ()=>{
  const s=setup({releaseExists:true,refError:Object.assign(new Error('No ref'),{status:404})});
  await checkReleaseTag(s.args);
  assert.equal(s.calls.length,1);
  assert.equal(s.failures.length,1);
  assert.match(s.failures[0],/already has a GitHub release/);
});

test('release lookup failures are propagated instead of allowing an overwrite', async ()=>{
  const error=Object.assign(new Error('API failure'),{status:403});
  const s=setup({releaseError:error});
  await assert.rejects(checkReleaseTag(s.args),err=>err===error);
  assert.equal(s.calls.length,1);
});
