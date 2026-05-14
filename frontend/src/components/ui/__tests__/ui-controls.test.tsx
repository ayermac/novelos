import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import {
  Checkbox,
  DataTable,
  FormField,
  NumberInput,
  Select,
  Switch,
  TextArea,
  TextInput,
} from '../index'

describe('ui controls', () => {
  it('renders form field label, helper, required marker, and error', () => {
    render(
      <>
        <FormField label="项目名" htmlFor="project-name" helper="用于工作台展示" required>
          <TextInput id="project-name" />
        </FormField>
        <FormField label="类型" htmlFor="genre" error="请选择类型">
          <Select id="genre" invalid>
            <option value="">选择</option>
          </Select>
        </FormField>
      </>,
    )

    expect(screen.getByLabelText(/项目名/)).toBeInTheDocument()
    expect(screen.getByText('*')).toBeInTheDocument()
    expect(screen.getByText('用于工作台展示')).toBeInTheDocument()
    expect(screen.getByText('请选择类型')).toBeInTheDocument()
    expect(screen.getByLabelText('类型')).toHaveAttribute('aria-invalid', 'true')
  })

  it('auto-associates form field labels and error descriptions with a single child control', () => {
    render(
      <FormField label="Base URL" error="请输入 Base URL">
        <TextInput />
      </FormField>,
    )

    const input = screen.getByLabelText('Base URL')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveClass('is-invalid')
    expect(input).toHaveAccessibleDescription('请输入 Base URL')
  })

  it('supports text, number, textarea, and select changes', () => {
    const onText = vi.fn()
    const onNumber = vi.fn()
    const onArea = vi.fn()
    const onSelect = vi.fn()
    render(
      <>
        <TextInput aria-label="文本" onChange={onText} />
        <NumberInput aria-label="数字" onChange={onNumber} />
        <TextArea aria-label="长文" onChange={onArea} />
        <Select aria-label="选项" defaultValue="a" onChange={onSelect}>
          <option value="a">A</option>
          <option value="b">B</option>
        </Select>
      </>,
    )

    fireEvent.change(screen.getByLabelText('文本'), { target: { value: 'abc' } })
    fireEvent.change(screen.getByLabelText('数字'), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText('长文'), { target: { value: 'body' } })
    fireEvent.change(screen.getByLabelText('选项'), { target: { value: 'b' } })

    expect(onText).toHaveBeenCalled()
    expect(onNumber).toHaveBeenCalled()
    expect(onArea).toHaveBeenCalled()
    expect(onSelect).toHaveBeenCalled()
  })

  it('preserves checkbox and switch native toggle behavior', () => {
    render(
      <>
        <Checkbox label="启用 Skill" />
        <Switch label="自动恢复" />
      </>,
    )

    fireEvent.click(screen.getByLabelText('启用 Skill'))
    fireEvent.click(screen.getByLabelText('自动恢复'))

    expect(screen.getByLabelText('启用 Skill')).toBeChecked()
    expect(screen.getByLabelText('自动恢复')).toBeChecked()
  })

  it('passes disabled and aria attributes through controls', () => {
    render(
      <>
        <TextInput aria-label="禁用输入" aria-describedby="hint" disabled />
        <Checkbox label="禁用复选" disabled />
        <Switch label="禁用开关" disabled />
      </>,
    )

    expect(screen.getByLabelText('禁用输入')).toBeDisabled()
    expect(screen.getByLabelText('禁用输入')).toHaveAttribute('aria-describedby', 'hint')
    expect(screen.getByLabelText('禁用复选')).toBeDisabled()
    expect(screen.getByLabelText('禁用开关')).toBeDisabled()
  })

  it('renders DataTable rows and empty state', () => {
    render(
      <>
        <DataTable
          columns={[{ key: 'name', header: '名称', render: (row: { name: string }) => row.name }]}
          data={[{ name: 'Author' }]}
          getRowKey={(row) => row.name}
        />
        <DataTable
          columns={[{ key: 'name', header: '名称', render: (row: { name: string }) => row.name }]}
          data={[]}
          getRowKey={(row) => row.name}
          emptyTitle="没有记录"
          emptyDescription="添加后会显示在这里"
        />
      </>,
    )

    expect(screen.getByRole('columnheader', { name: '名称' })).toBeInTheDocument()
    expect(screen.getByText('Author')).toBeInTheDocument()
    expect(screen.getByText('没有记录')).toBeInTheDocument()
    expect(screen.getByText('添加后会显示在这里')).toBeInTheDocument()
  })
})
