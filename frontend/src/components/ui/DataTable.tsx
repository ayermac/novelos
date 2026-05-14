import type { ReactNode } from 'react'
import { EmptyState } from './EmptyState'

export interface DataTableColumn<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  className?: string
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  data: T[]
  getRowKey: (row: T, index: number) => string
  emptyTitle?: ReactNode
  emptyDescription?: ReactNode
  className?: string
  compact?: boolean
}

export function DataTable<T>({ columns, data, getRowKey, emptyTitle = '暂无数据', emptyDescription, className = '', compact = false }: DataTableProps<T>) {
  if (data.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />
  }

  return (
    <div className={`ui-data-table-wrap ${className}`.trim()}>
      <table className={`ui-data-table ${compact ? 'is-compact' : ''}`.trim()}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.className}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <tr key={getRowKey(row, index)}>
              {columns.map((column) => (
                <td key={column.key} className={column.className}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
