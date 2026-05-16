import type { HTMLAttributes } from 'react'

export interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  width?: string | number
  height?: string | number
  radius?: string | number
}

export function Skeleton({ className = '', width, height, radius, style, ...props }: SkeletonProps) {
  return (
    <div
      className={`ui-skeleton ${className}`.trim()}
      aria-hidden="true"
      style={{ width, height, borderRadius: radius, ...style }}
      {...props}
    />
  )
}

export function SkeletonStack({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`ui-skeleton-stack ${className}`.trim()} aria-hidden="true">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} height={index === 0 ? 18 : 12} width={index === rows - 1 ? '72%' : '100%'} />
      ))}
    </div>
  )
}
