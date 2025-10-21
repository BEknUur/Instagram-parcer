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
  ocrText?: string;
}

interface PostComments {
  [shortCode: string]: {
    loading: boolean;
    comments: any[];
    error: string | null;
  };
}

interface OCRResult {
  text: string;
  confidence: number;
  details: Array<{
    text: string;
    confidence: number;
  }>;
  has_text: boolean;
}

interface OCRData {
  [filename: string]: OCRResult;
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
  const [commentLimits, setCommentLimits] = useState<{ [key: string]: number }>({})
  const [postsPerPage, setPostsPerPage] = useState(15)
  const [currentPage, setCurrentPage] = useState(1)
  const [searchPostsText, setSearchPostsText] = useState('')
  const [ocrData, setOcrData] = useState<OCRData | null>(null)
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrAttempt, setOcrAttempt] = useState(0)

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

      // Пытаемся загрузить OCR результаты с повторными попытками
      // (так как OCR выполняется в фоне и может занять время)
      if (data.runId) {
        loadOCRResultsWithRetry(data.runId)
      }

    } catch (err: any) {
      setError(err.message || 'Произошла ошибка при загрузке данных')
    } finally {
      setLoading(false)
    }
  }

  // Функция для загрузки OCR результатов с повторными попытками
  const loadOCRResultsWithRetry = async (runId: string, attempt: number = 1, maxAttempts: number = 6) => {
    setOcrLoading(true)
    setOcrAttempt(attempt)

    try {
      const response = await fetch(
        `${API_BASE_URL}/get-ocr-results?run_id=${encodeURIComponent(runId)}`
      )

      if (response.ok) {
        const data = await response.json()
        setOcrData(data.ocr_results)
        console.log(`✅ Загружено OCR для ${data.images_with_text}/${data.total_images} изображений`)
        setOcrLoading(false)
        setOcrAttempt(0)
      } else if (attempt < maxAttempts) {
        // Повторяем попытку с увеличивающейся задержкой
        const delay = attempt * 10000 // 10, 20, 30, 40, 50 секунд
        console.log(`OCR попытка ${attempt}/${maxAttempts}, следующая попытка через ${delay / 1000}с...`)
        setTimeout(() => loadOCRResultsWithRetry(runId, attempt + 1, maxAttempts), delay)
      } else {
        console.log('OCR результаты недоступны после всех попыток')
        setOcrLoading(false)
        setOcrAttempt(0)
      }
    } catch (err: any) {
      if (attempt < maxAttempts) {
        const delay = attempt * 10000
        setTimeout(() => loadOCRResultsWithRetry(runId, attempt + 1, maxAttempts), delay)
      } else {
        console.log('OCR результаты недоступны:', err.message)
        setOcrLoading(false)
        setOcrAttempt(0)
      }
    }
  }

  // Функция для загрузки OCR результатов (для ручного вызова)
  const loadOCRResults = async (runId: string) => {
    setOcrLoading(true)
    try {
      const response = await fetch(
        `${API_BASE_URL}/get-ocr-results?run_id=${encodeURIComponent(runId)}`
      )

      if (response.ok) {
        const data = await response.json()
        setOcrData(data.ocr_results)
        console.log(`✅ Загружено OCR для ${data.images_with_text}/${data.total_images} изображений`)
      } else {
        console.log('OCR результаты пока недоступны (возможно, обработка еще идет)')
      }
    } catch (err: any) {
      console.log('OCR результаты недоступны:', err.message)
    } finally {
      setOcrLoading(false)
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
    // В режиме 'posts', информация о профиле дублируется в каждом посте.
    // Берем из первого поста.
    const postData = data[0]
    return {
      username: postData.ownerUsername || '',
      fullName: postData.ownerFullName || '',
      biography: '', // В данных поста нет биографии
      followersCount: 0, // и количества подписчиков
      followsCount: 0,
      postsCount: 0,
      verified: postData.ownerIsVerified || false,
      private: false,
      profilePicUrl: postData.ownerProfilePicUrl || ''
    }
  }

  // Извлекаем тексты постов
  const extractCaptions = (data: any[]): PostCaption[] => {
    // В режиме 'posts', data - это уже массив постов
    return data.map((post, index) => {
      // Собираем OCR текст для всех изображений поста
      let ocrText = ''
      if (ocrData) {
        // Изображения нумеруются с 001, и каждый пост может иметь несколько изображений
        // Для упрощения берем первые 15 изображений и пытаемся найти соответствующие OCR результаты
        const imageIndex = String(index + 1).padStart(3, '0')
        const possibleFiles = [`${imageIndex}.jpg`, `${imageIndex}.jpeg`, `${imageIndex}.png`]

        for (const filename of possibleFiles) {
          if (ocrData[filename] && ocrData[filename].has_text) {
            ocrText = ocrData[filename].text
            break
          }
        }
      }

      return {
        text: post.caption || '',
        timestamp: post.timestamp || '',
        likesCount: post.likesCount || 0,
        commentsCount: post.commentsCount || 0,
        shortCode: post.shortCode || post.url?.split('/p/')[1]?.split('/')[0] || '',
        ocrText: ocrText
      }
    })
  }

  // Фильтруем посты по поисковому тексту
  const filterCaptions = (captions: PostCaption[]): PostCaption[] => {
    if (!searchPostsText.trim()) return captions
    const search = searchPostsText.toLowerCase()
    return captions.filter(caption =>
      caption.text.toLowerCase().includes(search) ||
      caption.shortCode?.toLowerCase().includes(search) ||
      (caption.ocrText && caption.ocrText.toLowerCase().includes(search))
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

            {/* OCR статус и кнопка загрузки */}
            <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
              {ocrData && (
                <div style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#d4edda',
                  color: '#155724',
                  borderRadius: '0.3rem',
                  fontSize: '0.9rem'
                }}>
                  📷 OCR: {Object.values(ocrData).filter(r => r.has_text).length} изображений с текстом
                </div>
              )}
              {ocrLoading && (
                <div style={{ fontSize: '0.9rem', color: '#666' }}>
                  ⏳ {ocrAttempt > 0 ? `Ожидание OCR (попытка ${ocrAttempt}/6)...` : 'Загрузка OCR результатов...'}
                </div>
              )}
              {!ocrData && !ocrLoading && result.runId && (
                <button
                  onClick={() => loadOCRResults(result.runId)}
                  style={{
                    padding: '0.5rem 1rem',
                    fontSize: '0.9rem',
                    borderRadius: '0.3rem',
                    border: '1px solid #007bff',
                    backgroundColor: '#fff',
                    color: '#007bff',
                    cursor: 'pointer'
                  }}
                >
                  🔍 Загрузить OCR результаты
                </button>
              )}
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
                        placeholder="🔍 Поиск по тексту, OCR или shortCode..."
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

                              {/* OCR текст с изображений */}
                              {caption.ocrText && (
                                <div style={{
                                  marginTop: '1rem',
                                  padding: '0.75rem',
                                  backgroundColor: '#f8f9fa',
                                  borderRadius: '0.5rem',
                                  borderLeft: '3px solid #007bff'
                                }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                                    <span style={{ fontSize: '0.9rem', fontWeight: 'bold', color: '#007bff' }}>
                                      📷 Текст с изображения:
                                    </span>
                                  </div>
                                  <p style={{
                                    margin: 0,
                                    fontSize: '0.95rem',
                                    color: '#333',
                                    fontStyle: 'italic',
                                    lineHeight: '1.5'
                                  }}>
                                    {caption.ocrText}
                                  </p>
                                </div>
                              )}

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
