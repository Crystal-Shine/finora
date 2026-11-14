"""Fills in your GitHub details. Usage:  python configure.py YOUR_GITHUB_USERNAME YOUR_REPO_NAME "Your Name" """
import sys
if len(sys.argv) < 3:
    sys.exit('Usage: python configure.py <github-username> <repo-name> ["Your Name"]')
user, repo = sys.argv[1], sys.argv[2]
name = sys.argv[3] if len(sys.argv) > 3 else user
for f in ['index.html', 'robots.txt', 'sitemap.xml', '404.html', 'README.md', 'LICENSE']:
    t = open(f, encoding='utf-8').read()
    t = t.replace('YOUR-USERNAME', user).replace('YOUR-REPO', repo).replace('YOUR-NAME', name)
    open(f, 'w', encoding='utf-8').write(t)
print(f'Done. Your site will live at https://{user}.github.io/{repo}/')
