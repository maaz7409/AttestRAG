# GitHub Actions workflows

`ci.yml` and `cd.yml` are the project's CI/CD pipelines. They live here because the
automated commit that created them did not have GitHub's `workflow` permission,
which is required to write into `.github/workflows/`.

Activate them with:

```bash
mkdir -p .github && git mv ci/github-workflows .github/workflows
git rm --cached .github/workflows/README.md && rm .github/workflows/README.md
git commit -m "Enable GitHub Actions CI/CD" && git push
```

(Or create the two files from the GitHub web UI under **Add file → Create new file**.)
