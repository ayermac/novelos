import type { ProjectModule } from '../components/project/ProjectModuleNav'

const CHAPTER_WORKBENCH_MODULES = new Set<ProjectModule>(['chapters'])

function isValidChapter(chapterNumber: number): boolean {
  return Number.isFinite(chapterNumber) && chapterNumber > 0
}

export function ensureChapterSearchParams(
  searchParams: URLSearchParams,
  fallbackChapter: number
): URLSearchParams {
  const next = new URLSearchParams(searchParams)
  if (!next.get('chapter') && isValidChapter(fallbackChapter)) {
    next.set('chapter', String(fallbackChapter))
  }
  return next
}

export function buildProjectModuleSearchParams(
  searchParams: URLSearchParams,
  module: ProjectModule,
  currentChapter: number
): URLSearchParams {
  const next = new URLSearchParams(searchParams)
  next.set('module', module)
  next.delete('auto_generate')

  if (isValidChapter(currentChapter)) {
    next.set('chapter', String(currentChapter))
  }

  if (!CHAPTER_WORKBENCH_MODULES.has(module)) {
    next.delete('view')
  }

  return next
}
