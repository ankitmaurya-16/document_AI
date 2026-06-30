import React, { useEffect, useState } from 'react'
import moment from 'moment'
import { useAppContext } from '../context/AppContext'

const fmtSize = (bytes) => {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

const Documents = () => {
  const { fetchDocuments, deleteDocument, user } = useAppContext()
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)

  const refresh = async () => {
    setLoading(true)
    const d = await fetchDocuments()
    setDocs(d)
    setLoading(false)
  }

  useEffect(() => {
    refresh()
  }, [user?._id])

  const handleDelete = async (doc) => {
    if (!window.confirm(`Delete "${doc.filename}"? Remaining documents will be re-indexed.`)) return
    setDeletingId(doc._id)
    const ok = await deleteDocument(doc._id)
    setDeletingId(null)
    if (ok) await refresh()
  }

  return (
    <div className='max-w-5xl h-screen overflow-y-auto mx-auto px-4 sm:px-6 lg:px-8 py-12'>
      <div className='flex items-center justify-between mb-8'>
        <h2 className='text-2xl font-semibold text-gray-800 dark:text-white'>My Documents</h2>
        <button
          onClick={refresh}
          className='text-sm px-3 py-1 border border-gray-300 dark:border-neutral-700 rounded hover:bg-gray-100 dark:hover:bg-neutral-800'>
          Refresh
        </button>
      </div>

      {loading ? (
        <p className='text-gray-500 dark:text-neutral-400'>Loading…</p>
      ) : docs.length === 0 ? (
        <div className='text-center py-20 text-gray-500 dark:text-neutral-400'>
          <p className='mb-2'>No documents uploaded yet.</p>
          <p className='text-sm'>Upload files from the chat window to see them here.</p>
        </div>
      ) : (
        <div className='border border-gray-200 dark:border-neutral-700 rounded-md overflow-hidden'>
          <table className='w-full text-sm'>
            <thead className='bg-gray-50 dark:bg-neutral-900 text-left'>
              <tr>
                <th className='py-2 px-4 font-medium text-gray-700 dark:text-neutral-300'>Filename</th>
                <th className='py-2 px-4 font-medium text-gray-700 dark:text-neutral-300'>Size</th>
                <th className='py-2 px-4 font-medium text-gray-700 dark:text-neutral-300'>Uploaded</th>
                <th className='py-2 px-4'></th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d._id} className='border-t border-gray-200 dark:border-neutral-800'>
                  <td className='py-2 px-4 dark:text-white'>{d.filename}</td>
                  <td className='py-2 px-4 text-gray-600 dark:text-neutral-400'>{fmtSize(d.size)}</td>
                  <td className='py-2 px-4 text-gray-600 dark:text-neutral-400'>
                    {d.uploadedAt ? moment(d.uploadedAt).fromNow() : '—'}
                  </td>
                  <td className='py-2 px-4 text-right'>
                    <button
                      disabled={deletingId === d._id}
                      onClick={() => handleDelete(d)}
                      className='text-red-600 hover:text-red-800 disabled:opacity-50'>
                      {deletingId === d._id ? 'Deleting…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default Documents
