import { useState } from 'react'
import './App.css'

interface InstagramData {
  success: boolean;
  runId: string;
  username: string;
  url: string;
  message: string;
  data: any[];
  stats: {
    total_items: number;
    profile_data: number;
    posts_with_comments: number;
    processing_time_seconds: number;
  };
}

interface ProfileInfo {
  username: string;
  fullName: string;
  biography: string;
  followersCount: number;
  followsCount: number;
  postsCount: number;
  verified: boolean;
  private: boolean;
  profilePicUrl: string;
}

interface PostCaption {
  text: string;
  timestamp: string;
  likesCount: number;
  commentsCount: number;
  shortCode?: string;
}

interface PostComments {
  [shortCode: string]: {
    loading: boolean;
    comments: any[];
    error: string | null;
  };
}

function App() {
  const [username, setUsername] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<InstagramData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showJson, setShowJson] = useState(false)
  const [showCaptions, setShowCaptions] = useState(true)
  const [showProfile, setShowProfile] = useState(true)
  const [postComments, setPostComments] = useState<PostComments>({})
  const [commentLimits, setCommentLimits] = useState<{[key: string]: number}>({})

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!username.trim()) {
      setError('Пожалуйста, введите username')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      // Убираем @ если пользователь его ввел
      const cleanUsername = username.replace('@', '').trim()
      const instagramUrl = `https://www.instagram.com/${cleanUsername}/`
      
      // Отправляем запрос к бэкенду
      const response = await fetch(
        `http://localhost:8001/start-scrape?url=${encodeURIComponent(instagramUrl)}&username=${encodeURIComponent(cleanUsername)}`
      )
      
      if (!response.ok) {
        throw new Error(`Ошибка ${response.status}: ${response.statusText}`)
      }
      
      const data = await response.json()
      setResult(data)
      
    } catch (err: any) {
      setError(err.message || 'Произошла ошибка при загрузке данных')
    } finally {
      setLoading(false)
    }
  }

  // Функция для загрузки комментариев конкретного поста
  const loadPostComments = async (shortCode: string) => {
    const postUrl = `https://www.instagram.com/p/${shortCode}/`
    const limit = commentLimits[shortCode] || 50
    
    // Устанавливаем состояние загрузки
    setPostComments(prev => ({
      ...prev,
      [shortCode]: { loading: true, comments: [], error: null }
    }))
    
    try {
      const response = await fetch(
        `http://localhost:8001/scrape-comments?post_urls=${encodeURIComponent(postUrl)}&results_limit=${limit}`
      )
      
      if (!response.ok) {
        throw new Error(`Ошибка ${response.status}`)
      }
      
      const data = await response.json()
      
      setPostComments(prev => ({
        ...prev,
        [shortCode]: {
          loading: false,
          comments: data.comments || [],
          error: null
        }
      }))
      
    } catch (err: any) {
      setPostComments(prev => ({
        ...prev,
        [shortCode]: {
          loading: false,
          comments: [],
          error: err.message || 'Ошибка загрузки комментариев'
        }
      }))
    }
  }

  // Извлекаем информацию о профиле
  const extractProfileInfo = (data: any[]): ProfileInfo | null => {
    if (!data || data.length === 0) return null
    const profileData = data[0]
    return {
      username: profileData.username || '',
      fullName: profileData.fullName || '',
      biography: profileData.biography || '',
      followersCount: profileData.followersCount || 0,
      followsCount: profileData.followsCount || 0,
      postsCount: profileData.postsCount || 0,
      verified: profileData.verified || false,
      private: profileData.private || false,
      profilePicUrl: profileData.profilePicUrl || ''
    }
  }

  // Извлекаем тексты постов
  const extractCaptions = (data: any[]): PostCaption[] => {
    const captions: PostCaption[] = []
    data.forEach(item => {
      if (item.latestPosts && Array.isArray(item.latestPosts)) {
        item.latestPosts.forEach((post: any) => {
          if (post.caption) {
            captions.push({
              text: post.caption,
              timestamp: post.timestamp || '',
              likesCount: post.likesCount || 0,
              commentsCount: post.commentsCount || 0,
              shortCode: post.shortCode || post.url?.split('/p/')[1]?.split('/')[0] || ''
            })
          }
        })
      }
    })
    return captions
  }

  return (
    <div className="container">
      <h1>Instagram Parser</h1>
      <p className="subtitle">Получите данные профиля и комментарии Instagram</p>
      
      <form onSubmit={handleSubmit} className="form">
        <div className="input-group">
          <input
                type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="@username"
            className="input"
            disabled={loading}
          />
          <button type="submit" className="button" disabled={loading}>
            {loading ? 'Загрузка...' : 'Получить данные'}
          </button>
        </div>
      </form>

      {error && (
        <div className="error">
          ❌ {error}
        </div>
      )}

      {loading && (
        <div className="loading">
          <div className="spinner"></div>
          <p>Парсим данные профиля... Это может занять несколько минут</p>
        </div>
      )}

      {result && (
        <div className="results">
          <div className="stats">
            <h2>✅ {result.message}</h2>
            <div className="stats-grid">
              <div className="stat-item">
                <span className="stat-label">Username:</span>
                <span className="stat-value">{result.username}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Всего элементов:</span>
                <span className="stat-value">{result.stats.total_items}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Run ID:</span>
                <span className="stat-value">{result.runId}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Время обработки:</span>
                <span className="stat-value">{result.stats.processing_time_seconds}с</span>
              </div>
            </div>
          </div>

          {/* Человеко-читаемая информация о профиле */}
          {(() => {
            const profile = extractProfileInfo(result.data)
            return profile && (
              <div className="profile-section">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h3>👤 Информация о профиле</h3>
                  <button 
                    onClick={() => setShowProfile(!showProfile)}
                    style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
                  >
                    {showProfile ? '🔼 Скрыть' : '🔽 Показать'}
                  </button>
                </div>
                {showProfile && (
                  <div className="profile-info">
                    {profile.profilePicUrl && (
                      <div className="profile-pic">
                        <img src={profile.profilePicUrl} alt={profile.username} />
                      </div>
                    )}
                    <div className="profile-details">
                      <div className="profile-row">
                        <span className="profile-label">Имя пользователя:</span>
                        <span className="profile-value">@{profile.username} {profile.verified && '✓'}</span>
                      </div>
                      <div className="profile-row">
                        <span className="profile-label">Полное имя:</span>
                        <span className="profile-value">{profile.fullName || 'Не указано'}</span>
                      </div>
                      {profile.biography && (
                        <div className="profile-row">
                          <span className="profile-label">Биография:</span>
                          <p className="profile-bio">{profile.biography}</p>
                        </div>
                      )}
                      <div className="profile-stats">
                        <div className="profile-stat">
                          <span className="stat-number">{profile.postsCount.toLocaleString()}</span>
                          <span className="stat-text">Постов</span>
                        </div>
                        <div className="profile-stat">
                          <span className="stat-number">{profile.followersCount.toLocaleString()}</span>
                          <span className="stat-text">Подписчиков</span>
                        </div>
                        <div className="profile-stat">
                          <span className="stat-number">{profile.followsCount.toLocaleString()}</span>
                          <span className="stat-text">Подписок</span>
                        </div>
                      </div>
                      {profile.private && (
                        <div className="profile-badge">🔒 Закрытый профиль</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })()}

          {/* Тексты постов */}
          {(() => {
            const captions = extractCaptions(result.data)
            return captions.length > 0 && (
              <div className="captions-section">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h3>📝 Тексты постов ({captions.length})</h3>
                  <button 
                    onClick={() => setShowCaptions(!showCaptions)}
                    style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
                  >
                    {showCaptions ? '🔼 Скрыть' : '🔽 Показать'}
                  </button>
                </div>
                {showCaptions && (
                  <div className="captions-list">
                    {captions.map((caption, index) => {
                      const shortCode = caption.shortCode || ''
                      const commentsState = postComments[shortCode]
                      
                      return (
                        <div key={index} className="caption-card">
                          <div className="caption-header">
                            <span className="caption-number">
                              Пост #{index + 1}
                              {shortCode && <span className="shortcode"> ({shortCode})</span>}
                            </span>
                            <span className="caption-date">
                              {caption.timestamp ? new Date(caption.timestamp).toLocaleDateString('ru-RU') : 'Дата неизвестна'}
                            </span>
                          </div>
                          <p className="caption-text">{caption.text}</p>
                          <div className="caption-stats">
                            <span>❤️ {caption.likesCount.toLocaleString()}</span>
                            <span>💬 {caption.commentsCount.toLocaleString()}</span>
                          </div>
                          
                          {/* Кнопка для загрузки комментариев */}
                          {shortCode && (
                            <div className="comments-controls">
                              <input
                                type="number"
                                min="1"
                                max="500"
                                value={commentLimits[shortCode] || 50}
                                onChange={(e) => setCommentLimits(prev => ({
                                  ...prev,
                                  [shortCode]: Number(e.target.value)
                                }))}
                                className="comment-limit-input"
                                placeholder="Лимит"
                              />
                              <button
                                onClick={() => loadPostComments(shortCode)}
                                disabled={commentsState?.loading}
                                className="load-comments-btn"
                              >
                                {commentsState?.loading ? '⏳ Загрузка...' : '💬 Загрузить комментарии'}
                              </button>
                            </div>
                          )}
                          
                          {/* Отображение комментариев */}
                          {commentsState?.error && (
                            <div className="comments-error">❌ {commentsState.error}</div>
                          )}
                          
                          {commentsState?.comments && commentsState.comments.length > 0 && (
                            <div className="post-comments-section">
                              <h4>💬 Комментарии ({commentsState.comments.length})</h4>
                              <div className="post-comments-list">
                                {commentsState.comments.map((comment: any, cIndex: number) => (
                                  <div key={cIndex} className="comment-item">
                                    <div className="comment-author">
                                      <strong>@{comment.ownerUsername || 'Аноним'}</strong>
                                      <span className="comment-date">
                                        {comment.timestamp ? new Date(comment.timestamp).toLocaleDateString('ru-RU') : ''}
                                      </span>
                                    </div>
                                    <p className="comment-text">{comment.text}</p>
                                    {comment.likesCount > 0 && (
                                      <span className="comment-likes">❤️ {comment.likesCount}</span>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })()}

          <div className="json-section">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3>📋 JSON данные (сырые)</h3>
              <button 
                onClick={() => setShowJson(!showJson)}
                style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
              >
                {showJson ? '🔼 Скрыть JSON' : '🔽 Показать JSON'}
              </button>
            </div>
            {showJson && (
              <pre className="json-output">
                {JSON.stringify(result.data, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default App
