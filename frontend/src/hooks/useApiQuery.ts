import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { get, post, put, del, type EnvelopeResponse } from '../lib/api'

/** Extract data from envelope, throw on error. */
function unwrap<T>(res: EnvelopeResponse<T>): T {
  if (!res.ok || res.error) {
    throw new Error(res.error?.message || '请求失败')
  }
  return res.data as T
}

/**
 * useApiQuery — wraps GET endpoints with the envelope pattern.
 *
 * @example
 * const { data, isLoading, error } = useApiQuery<Workspace>(['workspace', id], `/projects/${id}/workspace`)
 */
export function useApiQuery<T>(
  key: QueryKey,
  path: string,
  options?: { enabled?: boolean; staleTime?: number },
) {
  return useQuery<T>({
    queryKey: key,
    queryFn: async () => {
      const res = await get<T>(path)
      return unwrap(res)
    },
    ...options,
  })
}

type HttpMethod = 'post' | 'put' | 'del'

interface UseApiMutationOptions<T, V> {
  method?: HttpMethod
  invalidateKeys?: QueryKey[]
  onSuccess?: (data: T, variables: V) => void
  onError?: (error: Error, variables: V) => void
}

/**
 * useApiMutation — wraps POST/PUT/DELETE endpoints.
 *
 * @example
 * const mutation = useApiMutation<unknown, { name: string }>(
 *   '/projects/demo',
 *   { method: 'put', invalidateKeys: [['workspace', 'demo']] }
 * )
 * mutation.mutate({ name: 'New Name' })
 */
export function useApiMutation<T = unknown, V = unknown>(
  path: string | ((variables: V) => string),
  options?: UseApiMutationOptions<T, V>,
) {
  const queryClient = useQueryClient()
  const method = options?.method ?? 'post'

  return useMutation<T, Error, V>({
    mutationFn: async (variables: V) => {
      const resolvedPath = typeof path === 'function' ? path(variables) : path
      const fn = method === 'put' ? put : method === 'del' ? del : post
      const res = await fn<T>(resolvedPath, variables)
      return unwrap(res)
    },
    onSuccess: (data, variables) => {
      if (options?.invalidateKeys) {
        for (const key of options.invalidateKeys) {
          queryClient.invalidateQueries({ queryKey: key })
        }
      }
      options?.onSuccess?.(data, variables)
    },
    onError: options?.onError,
  })
}
