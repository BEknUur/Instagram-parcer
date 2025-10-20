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
  const [postsPerPage, setPostsPerPage] = useState(15)
  const [currentPage, setCurrentPage] = useState(1)
  const [searchPostsText, setSearchPostsText] = useState('')

  // Определяем API URL в зависимости от окружения
  const API_BASE_URL = window.location.hostname === 'localhost' 
    ? 'http://localhost:8001' 
    : '/api';

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
        `${API_BASE_URL}/start-scrape?url=${encodeURIComponent(instagramUrl)}&username=${encodeURIComponent(cleanUsername)}`
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
        `${API_BASE_URL}/scrape-comments?post_urls=${encodeURIComponent(postUrl)}&results_limit=${limit}`
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

  // Фильтруем посты по поисковому тексту
  const filterCaptions = (captions: PostCaption[]): PostCaption[] => {
    if (!searchPostsText.trim()) return captions
    const search = searchPostsText.toLowerCase()
    return captions.filter(caption => 
      caption.text.toLowerCase().includes(search) ||
      caption.shortCode?.toLowerCase().includes(search)
    )
  }

  // Пагинация постов
  const getPaginatedCaptions = (captions: PostCaption[]): { captions: PostCaption[], totalPages: number } => {
    const filtered = filterCaptions(captions)
    const totalPages = Math.ceil(filtered.length / postsPerPage)
    const startIndex = (currentPage - 1) * postsPerPage
    const endIndex = startIndex + postsPerPage
    return {
      captions: filtered.slice(startIndex, endIndex),
      totalPages
    }
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
            const allCaptions = extractCaptions(result.data)
            const { captions, totalPages } = getPaginatedCaptions(allCaptions)
            const filteredTotal = filterCaptions(allCaptions).length
            
            return allCaptions.length > 0 && (
              <div className="captions-section">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <h3>📝 Тексты постов ({filteredTotal}/{allCaptions.length})</h3>
                  <button 
                    onClick={() => setShowCaptions(!showCaptions)}
                    style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
                  >
                    {showCaptions ? '🔼 Скрыть' : '🔽 Показать'}
                  </button>
                </div>
                
                {showCaptions && (
                  <>
                    {/* Поисковая строка */}
                    <div style={{ marginBottom: '1rem' }}>
                      <input
                        type="text"
                        placeholder="🔍 Поиск по тексту или shortCode..."
                        value={searchPostsText}
                        onChange={(e) => {
                          setSearchPostsText(e.target.value)
                          setCurrentPage(1) // Сбрасываем на первую страницу при поиске
                        }}
                        style={{
                          width: '100%',
                          padding: '0.75rem',
                          borderRadius: '0.5rem',
                          border: '1px solid #ddd',
                          fontSize: '1rem',
                          fontFamily: 'inherit'
                        }}
                      />
                    </div>

                    {/* Настройки отображения */}
                    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <label htmlFor="posts-per-page" style={{ fontSize: '0.9rem' }}>Постов на странице:</label>
                        <select
                          id="posts-per-page"
                          value={postsPerPage}
                          onChange={(e) => {
                            setPostsPerPage(Number(e.target.value))
                            setCurrentPage(1)
                          }}
                          style={{
                            padding: '0.5rem',
                            borderRadius: '0.3rem',
                            border: '1px solid #ddd',
                            fontSize: '0.9rem'
                          }}
                        >
                          <option value={10}>10</option>
                          <option value={15}>15</option>
                          <option value={25}>25</option>
                          <option value={50}>50</option>
                        </select>
                      </div>
                      <span style={{ fontSize: '0.9rem', color: '#666' }}>
                        Страница {currentPage} из {totalPages > 0 ? totalPages : 1}
                      </span>
                    </div>

                    {/* Список постов */}
                    <div className="captions-list">
                      {captions.length > 0 ? (
                        captions.map((caption, index) => {
                          const shortCode = caption.shortCode || ''
                          const commentsState = postComments[shortCode]
                          const globalIndex = (currentPage - 1) * postsPerPage + index + 1
                          
                          return (
                            <div key={index} className="caption-card">
                              <div className="caption-header">
                                <span className="caption-number">
                                  Пост #{globalIndex}
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
                        })
                      ) : (
                        <p style={{ textAlign: 'center', color: '#666', padding: '2rem' }}>
                          {searchPostsText ? 'По вашему запросу постов не найдено' : 'Нет постов для отображения'}
                        </p>
                      )}
                    </div>

                    {/* Пагинация */}
                    {totalPages > 1 && (
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'center', 
                        gap: '0.5rem', 
                        marginTop: '2rem',
                        flexWrap: 'wrap'
                      }}>
                        <button
                          onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                          disabled={currentPage === 1}
                          style={{
                            padding: '0.5rem 1rem',
                            borderRadius: '0.3rem',
                            border: '1px solid #ddd',
                            background: currentPage === 1 ? '#f0f0f0' : '#fff',
                            cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                            opacity: currentPage === 1 ? 0.5 : 1
                          }}
                        >
                          ← Предыдущая
                        </button>
                        
                        {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                          <button
                            key={page}
                            onClick={() => setCurrentPage(page)}
                            style={{
                              padding: '0.5rem 0.75rem',
                              borderRadius: '0.3rem',
                              border: '1px solid #ddd',
                              background: currentPage === page ? '#007bff' : '#fff',
                              color: currentPage === page ? '#fff' : '#000',
                              cursor: 'pointer',
                              fontWeight: currentPage === page ? 'bold' : 'normal'
                            }}
                          >
                            {page}
                          </button>
                        ))}
                        
                        <button
                          onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                          disabled={currentPage === totalPages}
                          style={{
                            padding: '0.5rem 1rem',
                            borderRadius: '0.3rem',
                            border: '1px solid #ddd',
                            background: currentPage === totalPages ? '#f0f0f0' : '#fff',
                            cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                            opacity: currentPage === totalPages ? 0.5 : 1
                          }}
                        >
                          Следующая →
                        </button>
                      </div>
                    )}
                  </>
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
