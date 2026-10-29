// An absent tag is expected for the first release of a version.
module.exports = async function checkReleaseTag({github, context, core, tag, testedSha}) {
  // Deleted tags can still have releases pointing at old commits. Never reuse
  // such a version: release actions can reuse that release and its stale tag.
  try {
    await github.rest.repos.getReleaseByTag({...context.repo, tag});
    core.setFailed(`${tag} already has a GitHub release. Choose a new version instead of overwriting it.`);
    return;
  } catch (error) {
    if (error.status !== 404) throw error;
  }
  try {
    await github.rest.git.getRef({...context.repo, ref: `tags/${tag}`});
  } catch (error) {
    if (error.status !== 404) throw error;
    core.info(`${tag} does not exist yet; the release will create it.`);
    return;
  }

  // Resolve an existing tag to its commit, including annotated tags.
  // Errors here must propagate: only a missing reference permits creation.
  const {data: commit} = await github.rest.repos.getCommit({
    ...context.repo, ref: `refs/tags/${tag}`,
  });
  if (commit.sha !== testedSha) {
    core.setFailed(`${tag} already points to another commit. Bump the manifest version before releasing.`);
  }
};
