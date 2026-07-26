# Cristián Navarrete — fresh Quarto website project

This is the clean, consolidated version of the academic website. It is ready to place in a new GitHub repository.

## Included updates

- Clean academic homepage with the profile portrait and research cards.
- Pink Kirby / “Health, science and society” brand assets.
- Source Sans 3-based typography and light/dark themes.
- Navbar logo without the extra textual site title.
- Publications generated from one YAML file, with:
  - published, preprint, working-paper, and in-print statuses;
  - publication types and action links;
  - a sticky Status/Year sidebar;
  - counts for every status and year;
  - the year-list indentation bug fixed.
- Goodreads gallery with ratings, dates, covers, and personal review blocks.
- Letterboxd gallery based only on `ratings.csv`, with:
  - locally cached poster images;
  - automatic matching to film-review posts under `posts/`;
  - optional exact matching through a `film:` field in post front matter.
- `.DS_Store`, Python cache, RStudio state, and Quarto cache files ignored by Git.

## Important: set the new GitHub repository URL

Before publishing, open `_quarto.yml` and replace these placeholders:

```yaml
site-url: https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/
repo-url: https://github.com/YOUR-USERNAME/YOUR-REPOSITORY
```

Also replace the matching link in `_brand.yml`.

For example, for a repository named `academic-site`:

```yaml
site-url: https://crisnavarrete.github.io/academic-site/
repo-url: https://github.com/crisnavarrete/academic-site
```

## Personal files

A profile image reconstructed from the supplied website screenshot is already included at:

```text
assets/images/profile.jpg
```

Add your current CV at:

```text
assets/documents/NavarreteC_CV.pdf
```

The original CV file was not available in the uploaded materials, so that file is not included.

Your existing blog posts and teaching pages were also not available as source files. Copy them into:

```text
posts/
classes/
```

## Main data files

```text
data/publications/papers.yaml
data/reading/goodreads_library_export.csv
data/films/letterboxd/ratings.csv
```

`watched.csv` and `reviews.csv` are retained in the Letterboxd data directory for reference, but the Films page intentionally uses `ratings.csv` only.

## Publication workflow

Edit only:

```text
data/publications/papers.yaml
```

Validate it with:

```bash
python3 -m src.site_components.publications data/publications/papers.yaml
```

The page is rendered through:

```text
data/publications/papers.yaml
            ↓
src/site_components/publications.py
            ↓
publications.qmd
            ↓
docs/publications.html
```

## Film-review matching

A film such as `Hamnet` will automatically match a blog post titled `Sobre Hamnet`.

For an exact override, add this to the post front matter:

```yaml
---
title: "A different title for the post"
film: "Hamnet"
---
```

Poster images are downloaded during rendering and cached in:

```text
assets/images/letterboxd/posters/
```

## Install and preview

From the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
quarto preview
```

For a production build:

```bash
quarto render
```

The generated site is written to `docs/`.

## Create the new Git repository

After editing the repository URLs and adding any missing personal files:

```bash
git init
git branch -M main
git add .
git commit -m "Initial website"
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

For GitHub Pages using the generated `docs/` folder, configure Pages to deploy from the `main` branch and `/docs` directory.

## Structure

```text
.
├── _quarto.yml
├── _brand.yml
├── index.qmd
├── about.qmd
├── publications.qmd
├── posts.qmd
├── classes.qmd
├── reading.qmd
├── films.qmd
├── assets/
│   ├── brand/
│   ├── documents/
│   ├── images/
│   ├── includes/
│   └── styles/
├── data/
│   ├── publications/
│   ├── reading/
│   └── films/letterboxd/
├── src/site_components/
├── posts/
├── classes/
└── docs/
```
