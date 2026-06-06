import type { ProjectModule } from '../components/project/ProjectModuleNav'

const CHAPTER_WORKBENCH_MODULES = new Set<ProjectModule>(['chapters'])
const PROJECT_MODULES = new Set<ProjectModule>([
  'overview',
  'chapters',
  'worldview',
  'characters',
  'factions',
  'outline',
  'plots',
  'instructions',
  'style',
  'review',
  'runs',
  'settings',
  'genesis',
  'memory',
  'facts',
  'creative-contracts',
])

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

export function resolveProjectModule(searchParams: URLSearchParams): ProjectModule {
  const explicitModule = searchParams.get('module') as ProjectModule | null
  if (explicitModule && PROJECT_MODULES.has(explicitModule)) {
    return explicitModule
  }
  return searchParams.get('chapter') ? 'chapters' : 'overview'
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
