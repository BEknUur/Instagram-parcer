import { useState } from 'react'
import './CommentsScraper.css'

interface CommentsResponse {
  success: boolean;
  runId: string;
  message: string;
  total_comments: number;
  posts_count: number;
  processing_time_seconds: number;
  comments: Comment[];
}

interface Comment {
  text: string;
  ownerUsername: string;
  timestamp?: string;
  likesCount?: number;
  url?: string;
}

function CommentsScraper() {
  const [postUrls, setPostUrls] = useState('')
  const [resultsLimit, setResultsLimit] = useState(100)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CommentsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!postUrls.trim()) {
      setError('Введите URL постов')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(
        `http://localhost:8001/scrape-comments?post_urls=${encodeURIComponent(postUrls)}&results_limit=${resultsLimit}`
      )
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `Ошибка ${response.status}`)
      }
      
      const data = await response.json()
      setResult(data)
      
    } catch (err: any) {
      setError(err.message || 'Ошибка загрузки комментариев')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="comments-scraper-container">
      <h2>💬 Парсер комментариев</h2>
      <p className="subtitle">Получите комментарии под постами Instagram</p>
      
      <form onSubmit={handleSubmit} className="form">
        <div className="form-group">
          <label>URL постов (через запятую):</label>
          <textarea
            value={postUrls}
            onChange={(e) => setPostUrls(e.target.value)}
            placeholder="https://www.instagram.com/p/ABC123, https://www.instagram.com/reel/DEF456"
            className="textarea"
            rows={4}
            disabled={loading}
          />
          <span className="hint">Можно указать до 50 постов</span>
        </div>
        
        <div className="form-group">
          <label>Максимум комментариев:</label>
          <input
            type="number"
            value={resultsLimit}
            onChange={(e) => setResultsLimit(Number(e.target.value))}
            min={1}
            max={1000}
            className="input"
            disabled={loading}
          />
        </div>
        
        <button type="submit" className="button" disabled={loading}>
          {loading ? 'Загрузка...' : 'Получить комментарии'}
        </button>
      </form>

      {error && (
        <div className="error">
          ❌ {error}
        </div>
      )}

      {loading && (
        <div className="loading">
          <div className="spinner"></div>
          <p>Парсим комментарии... Подождите немного</p>
        </div>
      )}

      {result && (
        <div className="results">
          <div className="stats">
            <h3>✅ {result.message}</h3>
            <div className="stats-grid">
              <div className="stat-item">
                <span className="stat-label">Комментариев:</span>
                <span className="stat-value">{result.total_comments}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Постов:</span>
                <span className="stat-value">{result.posts_count}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Время:</span>
                <span className="stat-value">{result.processing_time_seconds}с</span>
              </div>
            </div>
          </div>

          <div className="comments-section">
            <h3>💬 Комментарии ({result.comments.length})</h3>
            <div className="comments-list">
              {result.comments.map((comment, index) => (
                <div key={index} className="comment-card">
                  <div className="comment-header">
                    <span className="comment-author">@{comment.ownerUsername}</span>
                    {comment.timestamp && (
                      <span className="comment-date">
                        {new Date(comment.timestamp).toLocaleDateString('ru-RU')}
                      </span>
                    )}
                  </div>
                  <p className="comment-text">{comment.text}</p>
                  {comment.likesCount !== undefined && (
                    <div className="comment-stats">
                      <span>❤️ {comment.likesCount}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CommentsScraper
