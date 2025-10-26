import { useState } from 'react'
import './App.css'

interface InstagramData {
  success: boolean;
  runId: string;
  username: string;
  url: string;
  message: string;
  data: any[];
  status?: string;
  stats: {
    total_items: number;
    profile_data: number;
    processing_time_seconds: number;
    images_status?: string;
  };
}

interface ScrapeStatus {
  success: boolean;
  run_id: string;
  status: string;
  details: {
    data_status: string;
    images_count: number;
    total_posts: number;
    created_at: string;
    images_started_at?: string;
    images_finished_at?: string;
    images_error?: string;
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

function App() {
  const [username, setUsername] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<InstagramData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showJson, setShowJson] = useState(false)
  const [showCaptions, setShowCaptions] = useState(true)
  const [showProfile, setShowProfile] = useState(true)
  const [postsPerPage, setPostsPerPage] = useState(15)
  const [currentPage, setCurrentPage] = useState(1)
  const [searchPostsText, setSearchPostsText] = useState('')
  const [images, setImages] = useState<string[]>([])
  const [showGallery, setShowGallery] = useState(true)
  const [imagesLoading, setImagesLoading] = useState(false)
  const [scrapeStatus, setScrapeStatus] = useState<ScrapeStatus | null>(null)

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

    // Функция для выполнения запроса с повторными попытками
    const makeRequestWithRetry = async (attempt: number = 1, maxAttempts: number = 3): Promise<any> => {
      try {
        // Убираем @ если пользователь его ввел
        const cleanUsername = username.replace('@', '').trim()
        const instagramUrl = `https://www.instagram.com/${cleanUsername}/`

        console.log(`📡 Попытка ${attempt}/${maxAttempts}: отправляем запрос к ${API_BASE_URL}/start-scrape`)

        // Создаем AbortController для управления таймаутом
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 120000) // 2 минуты таймаут

        try {
          // Отправляем запрос к бэкенду с увеличенным таймаутом
          const response = await fetch(
            `${API_BASE_URL}/start-scrape?url=${encodeURIComponent(instagramUrl)}&username=${encodeURIComponent(cleanUsername)}`,
            {
              signal: controller.signal,
              headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
              }
            }
          )

          clearTimeout(timeoutId)

          if (!response.ok) {
            // Специальная обработка для 499 ошибки
            if (response.status === 499) {
              throw new Error('Соединение было закрыто браузером. Это может произойти при долгом выполнении запроса. Попробуйте еще раз.')
            }
            throw new Error(`Ошибка ${response.status}: ${response.statusText}`)
          }

          const data = await response.json()
          console.log(`✅ Запрос успешен с попытки ${attempt}:`, data)
          return data

        } catch (fetchErr: any) {
          clearTimeout(timeoutId)

          if (fetchErr.name === 'AbortError') {
            throw new Error(`Превышено время ожидания запроса (2 минуты). Попытка ${attempt}/${maxAttempts}.`)
          }

          throw fetchErr
        }

      } catch (err: any) {
        console.log(`❌ Попытка ${attempt} не удалась:`, err.message)

        if (attempt < maxAttempts) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 10000) // Экспоненциальная задержка, максимум 10 секунд
          console.log(`⏳ Ждем ${delay / 1000}с перед следующей попыткой...`)

          await new Promise(resolve => setTimeout(resolve, delay))
          return makeRequestWithRetry(attempt + 1, maxAttempts)
        }

        throw err
      }
    }

    try {
      const data = await makeRequestWithRetry()
      setResult(data)

      // Запускаем мониторинг статуса и загрузку изображений
      if (data.runId) {
        loadImagesWithRetry(data.runId)
        // Также запускаем мониторинг статуса для более точного отслеживания
        checkScrapeStatus(data.runId)
      }

    } catch (err: any) {
      console.error('❌ Все попытки исчерпаны:', err)
      setError(err.message || 'Произошла ошибка при загрузке данных. Попробуйте еще раз.')
    } finally {
      setLoading(false)
    }
  }

  // Функция для проверки статуса парсинга
  const checkScrapeStatus = async (runId: string, attempt: number = 1, maxAttempts: number = 20) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/scrape-status?run_id=${encodeURIComponent(runId)}`
      )

      if (response.ok) {
        const statusData = await response.json()
        setScrapeStatus(statusData)

        // Если изображения готовы или есть ошибка, останавливаемся
        if (statusData.status === 'completed') {
          console.log(`✅ Парсинг завершен: ${statusData.details.images_count} изображений`)
          // Загружаем изображения если они готовы
          if (statusData.details.images_count > 0) {
            loadImages(runId)
          }
          return
        } else if (statusData.status === 'error') {
          console.log('❌ Ошибка при загрузке изображений:', statusData.details.images_error)
          return
        }

        // Если еще не готово и не превысили максимум попыток
        if (attempt < maxAttempts) {
          const delay = 10000 // 10 секунд
          console.log(`⏳ Статус: ${statusData.status}, проверяем снова через ${delay / 1000}с...`)
          setTimeout(() => checkScrapeStatus(runId, attempt + 1, maxAttempts), delay)
        } else {
          console.log('⏱️ Превышено максимальное количество попыток проверки статуса')
        }
      } else if (attempt < maxAttempts) {
        const delay = 10000 // 10 секунд
        setTimeout(() => checkScrapeStatus(runId, attempt + 1, maxAttempts), delay)
      }
    } catch (err: any) {
      if (attempt < maxAttempts) {
        const delay = 10000 // 10 секунд
        setTimeout(() => checkScrapeStatus(runId, attempt + 1, maxAttempts), delay)
      } else {
        console.log('❌ Ошибка проверки статуса:', err.message)
      }
    }
  }

  // Функция для загрузки списка изображений
  const loadImages = async (runId: string) => {
    setImagesLoading(true)
    try {
      const response = await fetch(
        `${API_BASE_URL}/get-images?run_id=${encodeURIComponent(runId)}`
      )

      if (response.ok) {
        const data = await response.json()
        setImages(data.images || [])
        console.log(`✅ Загружено ${data.total_images} изображений`)
      } else {
        console.log('Изображения пока недоступны')
      }
    } catch (err: any) {
      console.log('Ошибка загрузки изображений:', err.message)
    } finally {
      setImagesLoading(false)
    }
  }

  // Функция для загрузки изображений с повторными попытками
  const loadImagesWithRetry = async (runId: string, attempt: number = 1, maxAttempts: number = 8) => {
    setImagesLoading(true)

    try {
      const response = await fetch(
        `${API_BASE_URL}/get-images?run_id=${encodeURIComponent(runId)}`
      )

      if (response.ok) {
        const data = await response.json()
        if (data.total_images > 0) {
          setImages(data.images || [])
          console.log(`✅ Загружено ${data.total_images} изображений`)
          setImagesLoading(false)
        } else if (attempt < maxAttempts) {
          // Изображения еще не готовы, пробуем снова
          const delay = attempt * 5000 // 5, 10, 15, 20, 25, 30, 35, 40 секунд
          console.log(`📸 Изображения загружаются (попытка ${attempt}/${maxAttempts}), следующая попытка через ${delay / 1000}с...`)
          setTimeout(() => loadImagesWithRetry(runId, attempt + 1, maxAttempts), delay)
        } else {
          console.log('Изображения не были загружены после всех попыток')
          setImagesLoading(false)
        }
      } else if (attempt < maxAttempts) {
        const delay = attempt * 5000
        setTimeout(() => loadImagesWithRetry(runId, attempt + 1, maxAttempts), delay)
      } else {
        console.log('Изображения недоступны после всех попыток')
        setImagesLoading(false)
      }
    } catch (err: any) {
      if (attempt < maxAttempts) {
        const delay = attempt * 5000
        setTimeout(() => loadImagesWithRetry(runId, attempt + 1, maxAttempts), delay)
      } else {
        console.log('Ошибка загрузки изображений:', err.message)
        setImagesLoading(false)
      }
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
    return data.map((post) => {
      return {
        text: post.caption || '',
        timestamp: post.timestamp || '',
        likesCount: post.likesCount || 0,
        commentsCount: post.commentsCount || 0,
        shortCode: post.shortCode || post.url?.split('/p/')[1]?.split('/')[0] || ''
      }
    })
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
      <p className="subtitle">Получите данные профиля Instagram с изображениями</p>

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

            {/* Статус загрузки изображений */}
            <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
              {scrapeStatus && (
                <>
                  {scrapeStatus.status === 'completed' && scrapeStatus.details.images_count > 0 && (
                    <div style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#d4edda',
                      color: '#155724',
                      borderRadius: '0.3rem',
                      fontSize: '0.9rem',
                      fontWeight: 'bold',
                      border: '1px solid #c3e6cb'
                    }}>
                      ✅ {scrapeStatus.details.images_count} фото загружено
                    </div>
                  )}
                  {scrapeStatus.status === 'images_loading' && (
                    <div style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#fff3cd',
                      color: '#856404',
                      borderRadius: '0.3rem',
                      fontSize: '0.9rem',
                      fontWeight: 'bold',
                      border: '1px solid #ffeaa7'
                    }}>
                      ⏳ Загружаем изображения... ({scrapeStatus.details.images_count || 0} загружено)
                    </div>
                  )}
                  {scrapeStatus.status === 'error' && (
                    <div style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#f8d7da',
                      color: '#721c24',
                      borderRadius: '0.3rem',
                      fontSize: '0.9rem',
                      fontWeight: 'bold',
                      border: '1px solid #f5c6cb'
                    }}>
                      ❌ Ошибка загрузки изображений
                    </div>
                  )}
                  {scrapeStatus.status === 'data_ready' && (
                    <div style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#d1ecf1',
                      color: '#0c5460',
                      borderRadius: '0.3rem',
                      fontSize: '0.9rem',
                      fontWeight: 'bold',
                      border: '1px solid #bee5eb'
                    }}>
                      ⏳ Данные получены, загружаем изображения...
                    </div>
                  )}
                </>
              )}
              {images.length > 0 && (
                <div style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#d1ecf1',
                  color: '#0c5460',
                  borderRadius: '0.3rem',
                  fontSize: '0.9rem',
                  fontWeight: 'bold'
                }}>
                  📸 {images.length} фото доступно
                </div>
              )}
              {imagesLoading && (
                <div style={{
                  fontSize: '0.9rem',
                  color: '#666',
                  padding: '0.5rem 1rem',
                  backgroundColor: '#fff3cd',
                  borderRadius: '0.3rem'
                }}>
                  🔄 Проверяем изображения...
                </div>
              )}
              {!imagesLoading && images.length === 0 && result.runId && (
                <button
                  onClick={() => loadImages(result.runId)}
                  style={{
                    padding: '0.5rem 1rem',
                    fontSize: '0.9rem',
                    borderRadius: '0.3rem',
                    border: '1px solid #17a2b8',
                    backgroundColor: '#fff',
                    color: '#17a2b8',
                    cursor: 'pointer'
                  }}
                >
                  📸 Загрузить изображения
                </button>
              )}
            </div>
          </div>

          {/* Галерея фотографий */}
          {images.length > 0 && (
            <div className="profile-section" style={{ marginTop: '2rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3>📸 Галерея фотографий ({images.length})</h3>
                <button
                  onClick={() => setShowGallery(!showGallery)}
                  className="button"
                  style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
                >
                  {showGallery ? '🔼 Скрыть' : '🔽 Показать'}
                </button>
              </div>
              {showGallery && (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
                  gap: '1.5rem',
                  marginTop: '1rem'
                }}>
                  {images.map((imageName, index) => {
                    const imageUrl = `${API_BASE_URL}/image/${result.runId}/${imageName}`

                    return (
                      <div key={index} style={{
                        border: '1px solid #e0e0e0',
                        borderRadius: '0.75rem',
                        overflow: 'hidden',
                        backgroundColor: '#fff',
                        boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
                        transition: 'transform 0.2s, box-shadow 0.2s',
                        cursor: 'pointer'
                      }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.transform = 'translateY(-4px)';
                          e.currentTarget.style.boxShadow = '0 8px 12px rgba(0,0,0,0.15)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.transform = 'translateY(0)';
                          e.currentTarget.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
                        }}>
                        <div style={{ position: 'relative' }}>
                          <img
                            src={imageUrl}
                            alt={`Photo ${index + 1}`}
                            style={{
                              width: '100%',
                              height: '250px',
                              objectFit: 'cover',
                              cursor: 'pointer'
                            }}
                            onClick={() => window.open(imageUrl, '_blank')}
                          />
                          <div style={{
                            position: 'absolute',
                            top: '0.5rem',
                            right: '0.5rem',
                            backgroundColor: 'rgba(0,0,0,0.6)',
                            color: 'white',
                            padding: '0.25rem 0.5rem',
                            borderRadius: '0.3rem',
                            fontSize: '0.75rem',
                            fontWeight: 'bold'
                          }}>
                            #{index + 1}
                          </div>
                        </div>
                        <div style={{ padding: '1rem' }}>
                          <div style={{
                            fontSize: '0.8rem',
                            color: '#999',
                            marginBottom: '0.75rem',
                            fontFamily: 'monospace'
                          }}>
                            {imageName}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

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
                          const globalIndex = (currentPage - 1) * postsPerPage + index + 1

                          return (
                            <div key={index} className="caption-card">
                              <div className="caption-header">
                                <span className="caption-number">
                                  Пост #{globalIndex}
                                  {caption.shortCode && <span className="shortcode"> ({caption.shortCode})</span>}
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
