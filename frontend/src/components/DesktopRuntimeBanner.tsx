import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, RefreshCw, RotateCcw, FolderOpen } from 'lucide-react'
import { get, getApiBase } from '../lib/api'
import { useAppDialog } from './AppDialogContext'
import { Spinner } from './ui/Spinner'

interface DesktopRuntimeStatus {
  status: string
  pid: number | null
  apiBaseUrl: string
  port: number
  startTime: string | null
  lastError: {
    exitCode: number | null
    signal: string | null
    timestamp: string
    reason: string
  } | null
}

export default function DesktopRuntimeBanner() {
  const isDesktop = typeof window !== 'undefined' && !!window.__NOVELOS_DESKTOP__
  const [visible, setVisible] = useState(false)
  const [failCount, setFailCount] = useState(0)
  const [restarting, setRestarting] = useState(false)
  const [status, setStatus] = useState<DesktopRuntimeStatus | null>(null)
  const dialog = useAppDialog()
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const ping = async () => {
    try {
      const res = await get('/health')
      const ok = res.ok && (res.data as { status?: string } | undefined)?.status === 'ok'
      if (ok) {
        setFailCount(0)
        setVisible(false)
      } else {
        setFailCount((c) => c + 1)
      }
    } catch {
      setFailCount((c) => c + 1)
    }
  }

  useEffect(() => {
    if (!isDesktop) return
    ping()
    intervalRef.current = setInterval(ping, 8000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [isDesktop])

  useEffect(() => {
    if (!isDesktop) return
    const unsub = window.__NOVELOS_DESKTOP__?.onRuntimeStatus?.((s) => {
      setStatus(s as DesktopRuntimeStatus)
      if (s.status === 'healthy') {
        setFailCount(0)
        setVisible(false)
      } else if (s.status === 'failed' || s.status === 'exited') {
        setFailCount((c) => Math.max(c, 2))
      }
    })
    return () => {
      unsub?.()
    }
  }, [isDesktop])

  useEffect(() => {
    if (!isDesktop) return
    if (failCount >= 2) {
      setVisible(true)
    }
  }, [failCount, isDesktop])

  const handleRetry = async () => {
    await ping()
  }

  const handleRestart = async () => {
    const ok = await dialog.confirm({
      title: '重启本地服务',
      message: '确定要重启本地后端服务吗？进行中的请求可能会中断。',
      tone: 'warning',
      confirmLabel: '重启',
    })
    if (!ok) return
    setRestarting(true)
    try {
      const res = await window.__NOVELOS_DESKTOP__?.restartSidecar?.()
      if (res?.success) {
        setFailCount(0)
        setVisible(false)
      } else {
        await dialog.alert({
          title: '重启失败',
          message: '本地服务未能成功重启，请检查日志。',
          tone: 'danger',
        })
      }
    } catch (err) {
      await dialog.alert({
        title: '重启失败',
        message: `错误: ${(err as Error).message}`,
        tone: 'danger',
      })
    }
    setRestarting(false)
  }

  const openLogsDir = () => window.__NOVELOS_DESKTOP__?.openLogsDir?.()

  if (!isDesktop || !visible) return null

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 300,
        background: '#fef2f2',
        borderBottom: '1px solid #fecaca',
        padding: '10px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '12px',
        fontSize: '13px',
        color: '#991b1b',
      }}
    >
      <AlertTriangle size={16} />
      <span style={{ fontWeight: 500 }}>本地后端服务连接中断</span>
      <span style={{ color: '#b91c1c', fontSize: '12px' }}>
        {status?.lastError?.reason || `apiBase: ${getApiBase()}`}
      </span>
      <div style={{ display: 'flex', gap: '8px', marginLeft: 'auto' }}>
        <button
          onClick={handleRetry}
          disabled={restarting}
          style={{
            padding: '4px 10px',
            borderRadius: '4px',
            border: '1px solid #fca5a5',
            background: '#fff',
            color: '#991b1b',
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <RefreshCw size={12} />
          重试连接
        </button>
        <button
          onClick={handleRestart}
          disabled={restarting}
          style={{
            padding: '4px 10px',
            borderRadius: '4px',
            border: '1px solid #fca5a5',
            background: '#fff',
            color: '#991b1b',
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          {restarting ? <Spinner size="sm" label="" /> : <RotateCcw size={12} />}
          重启本地服务
        </button>
        <button
          onClick={openLogsDir}
          style={{
            padding: '4px 10px',
            borderRadius: '4px',
            border: '1px solid #fca5a5',
            background: '#fff',
            color: '#991b1b',
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <FolderOpen size={12} />
          打开日志目录
        </button>
      </div>
    </div>
  )
}
