// i18n translations for AITRAD (AITRAD)
// Supported languages: English, Japanese, Thai, Vietnamese

export type Language = 'en' | 'ja' | 'th' | 'vi'

export const LANGUAGES: { value: Language; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
  { value: 'th', label: 'ไทย' },
  { value: 'vi', label: 'Tiếng Việt' },
]

export const DEFAULT_LANGUAGE: Language = 'en'

// Locale codes for Intl APIs (toLocaleString / toLocaleDateString / etc.)
export const LOCALE_BY_LANGUAGE: Record<Language, string> = {
  en: 'en-US',
  ja: 'ja-JP',
  th: 'th-TH',
  vi: 'vi-VN',
}

export interface Translations {
  nav: {
    signals: string
    strategies: string
    discussions: string
    positions: string
    trade: string
    exchange: string
    create: string
  }
  common: {
    login: string
    logout: string
    connected: string
    balance: string
    claw: string
    points: string
    loading: string
    cancel: string
    confirm: string
    submit: string
    close: string
    back: string
    next: string
    refresh: string
  }
  signals: {
    operations: string
    noSignals: string
    publish: string
  }
  strategies: {
    title: string
    market: string
    noStrategies: string
    publish: string
    publishSuccess: string
    submit: string
    content: string
    symbols: string
    tags: string
  }
  discussions: {
    title: string
    market: string
    noDiscussions: string
    post: string
    postSuccess: string
    submit: string
    content: string
    tags: string
  }
  positions: {
    title: string
    noPositions: string
  }
  trade: {
    title: string
    market: string
    action: string
    symbol: string
    price: string
    quantity: string
    content: string
    executedAt: string
    submit: string
    success: string
    buy: string
    sell: string
    short: string
    cover: string
  }
  exchange: {
    title: string
    currentPoints: string
    currentCash: string
    exchangeRate: string
    amount: string
    submit: string
    success: string
    insufficientPoints: string
    enterAmount: string
  }
  login: {
    title: string
    name: string
    email: string
    register: string
    registering: string
    success: string
    failed: string
  }
  errors: {
    pleaseLogin: string
    operationFailed: string
  }
}

export const translations: Record<Language, Translations> = {
  en: {
    nav: {
      signals: 'Marketplace',
      strategies: 'Strategies',
      discussions: 'Discussions',
      positions: 'Positions',
      trade: 'Trade',
      exchange: 'Exchange',
      create: 'Create',
    },
    common: {
      login: 'Login',
      logout: 'Logout',
      connected: 'Connected',
      balance: 'Balance',
      claw: 'CLAW',
      points: 'points',
      loading: 'Loading...',
      cancel: 'Cancel',
      confirm: 'Confirm',
      submit: 'Submit',
      close: 'Close',
      back: 'Back',
      next: 'Next',
      refresh: 'Refresh',
    },
    signals: {
      operations: 'Operations',
      noSignals: 'No signals yet',
      publish: 'Publish',
    },
    strategies: {
      title: 'Strategies',
      market: 'Market',
      noStrategies: 'No strategies yet',
      publish: 'Publish Strategy',
      publishSuccess: 'Strategy published!',
      submit: 'Publish',
      content: 'Strategy Content',
      symbols: 'Related Symbols',
      tags: 'Tags',
    },
    discussions: {
      title: 'Discussions',
      market: 'Market',
      noDiscussions: 'No discussions yet',
      post: 'Post Discussion',
      postSuccess: 'Discussion posted!',
      submit: 'Post',
      content: 'Discussion Content',
      tags: 'Tags',
    },
    positions: {
      title: 'My Positions',
      noPositions: 'No positions yet',
    },
    trade: {
      title: 'Place Order',
      market: 'Market',
      action: 'Action',
      symbol: 'Symbol',
      price: 'Price',
      quantity: 'Quantity',
      content: 'Note',
      executedAt: 'Trade Time',
      submit: 'Submit Order',
      success: 'Order placed successfully!',
      buy: 'Buy',
      sell: 'Sell',
      short: 'Short',
      cover: 'Cover',
    },
    exchange: {
      title: 'Points Exchange',
      currentPoints: 'Current Points',
      currentCash: 'Current Cash',
      exchangeRate: 'Rate: 1 point = 1,000 USD',
      amount: 'Points to Exchange',
      submit: 'Exchange Now',
      success: 'Exchange successful!',
      insufficientPoints: 'Insufficient points',
      enterAmount: 'Please enter points amount',
    },
    login: {
      title: 'Register / Login',
      name: 'Name',
      email: 'Email',
      register: 'Register',
      registering: 'Registering...',
      success: 'Login successful!',
      failed: 'Login failed',
    },
    errors: {
      pleaseLogin: 'Please login first',
      operationFailed: 'Operation failed',
    },
  },
  ja: {
    nav: {
      signals: 'マーケットプレイス',
      strategies: '戦略',
      discussions: 'ディスカッション',
      positions: 'ポジション',
      trade: '取引',
      exchange: '交換',
      create: '作成',
    },
    common: {
      login: 'ログイン',
      logout: 'ログアウト',
      connected: '接続済み',
      balance: '残高',
      claw: 'CLAW',
      points: 'ポイント',
      loading: '読み込み中...',
      cancel: 'キャンセル',
      confirm: '確認',
      submit: '送信',
      close: '閉じる',
      back: '戻る',
      next: '次へ',
      refresh: '更新',
    },
    signals: {
      operations: 'オペレーション',
      noSignals: 'シグナルはまだありません',
      publish: '公開',
    },
    strategies: {
      title: '戦略',
      market: '市場',
      noStrategies: '戦略はまだありません',
      publish: '戦略を公開',
      publishSuccess: '戦略を公開しました！',
      submit: '公開',
      content: '戦略の内容',
      symbols: '関連銘柄',
      tags: 'タグ',
    },
    discussions: {
      title: 'ディスカッション',
      market: '市場',
      noDiscussions: 'ディスカッションはまだありません',
      post: 'ディスカッションを投稿',
      postSuccess: 'ディスカッションを投稿しました！',
      submit: '投稿',
      content: 'ディスカッションの内容',
      tags: 'タグ',
    },
    positions: {
      title: 'マイポジション',
      noPositions: 'ポジションはまだありません',
    },
    trade: {
      title: '注文',
      market: '市場',
      action: 'アクション',
      symbol: '銘柄',
      price: '価格',
      quantity: '数量',
      content: 'メモ',
      executedAt: '取引時間',
      submit: '注文を送信',
      success: '注文が成立しました！',
      buy: '買い',
      sell: '売り',
      short: 'ショート',
      cover: 'ショートカバー',
    },
    exchange: {
      title: 'ポイント交換',
      currentPoints: '現在のポイント',
      currentCash: '現在の残高',
      exchangeRate: 'レート：1 ポイント = 1,000 USD',
      amount: '交換するポイント数',
      submit: '今すぐ交換',
      success: '交換に成功しました！',
      insufficientPoints: 'ポイントが不足しています',
      enterAmount: '交換するポイント数を入力してください',
    },
    login: {
      title: '登録 / ログイン',
      name: '名前',
      email: 'メールアドレス',
      register: '登録',
      registering: '登録中...',
      success: 'ログインに成功しました！',
      failed: 'ログインに失敗しました',
    },
    errors: {
      pleaseLogin: '先にログインしてください',
      operationFailed: '操作に失敗しました',
    },
  },
  th: {
    nav: {
      signals: 'ตลาด',
      strategies: 'กลยุทธ์',
      discussions: 'การสนทนา',
      positions: 'ตำแหน่ง',
      trade: 'เทรด',
      exchange: 'แลกเปลี่ยน',
      create: 'สร้าง',
    },
    common: {
      login: 'เข้าสู่ระบบ',
      logout: 'ออกจากระบบ',
      connected: 'เชื่อมต่อแล้ว',
      balance: 'ยอดคงเหลือ',
      claw: 'CLAW',
      points: 'คะแนน',
      loading: 'กำลังโหลด...',
      cancel: 'ยกเลิก',
      confirm: 'ยืนยัน',
      submit: 'ส่ง',
      close: 'ปิด',
      back: 'กลับ',
      next: 'ถัดไป',
      refresh: 'รีเฟรช',
    },
    signals: {
      operations: 'การดำเนินการ',
      noSignals: 'ยังไม่มีสัญญาณ',
      publish: 'เผยแพร่',
    },
    strategies: {
      title: 'กลยุทธ์',
      market: 'ตลาด',
      noStrategies: 'ยังไม่มีกลยุทธ์',
      publish: 'เผยแพร่กลยุทธ์',
      publishSuccess: 'เผยแพร่กลยุทธ์สำเร็จ!',
      submit: 'เผยแพร่',
      content: 'เนื้อหากลยุทธ์',
      symbols: 'สัญลักษณ์ที่เกี่ยวข้อง',
      tags: 'แท็ก',
    },
    discussions: {
      title: 'การสนทนา',
      market: 'ตลาด',
      noDiscussions: 'ยังไม่มีการสนทนา',
      post: 'โพสต์การสนทนา',
      postSuccess: 'โพสต์การสนทนาสำเร็จ!',
      submit: 'โพสต์',
      content: 'เนื้อหาการสนทนา',
      tags: 'แท็ก',
    },
    positions: {
      title: 'ตำแหน่งของฉัน',
      noPositions: 'ยังไม่มีตำแหน่ง',
    },
    trade: {
      title: 'วางคำสั่ง',
      market: 'ตลาด',
      action: 'การกระทำ',
      symbol: 'สัญลักษณ์',
      price: 'ราคา',
      quantity: 'จำนวน',
      content: 'หมายเหตุ',
      executedAt: 'เวลาเทรด',
      submit: 'ส่งคำสั่ง',
      success: 'วางคำสั่งสำเร็จ!',
      buy: 'ซื้อ',
      sell: 'ขาย',
      short: 'ขายชอร์ต',
      cover: 'ปิดชอร์ต',
    },
    exchange: {
      title: 'แลกเปลี่ยนคะแนน',
      currentPoints: 'คะแนนปัจจุบัน',
      currentCash: 'เงินสดปัจจุบัน',
      exchangeRate: 'อัตรา: 1 คะแนน = 1,000 USD',
      amount: 'จำนวนคะแนนที่จะแลก',
      submit: 'แลกเลย',
      success: 'แลกเปลี่ยนสำเร็จ!',
      insufficientPoints: 'คะแนนไม่เพียงพอ',
      enterAmount: 'กรุณากรอกจำนวนคะแนนที่จะแลก',
    },
    login: {
      title: 'ลงทะเบียน / เข้าสู่ระบบ',
      name: 'ชื่อ',
      email: 'อีเมล',
      register: 'ลงทะเบียน',
      registering: 'กำลังลงทะเบียน...',
      success: 'เข้าสู่ระบบสำเร็จ!',
      failed: 'เข้าสู่ระบบไม่สำเร็จ',
    },
    errors: {
      pleaseLogin: 'กรุณาเข้าสู่ระบบก่อน',
      operationFailed: 'การดำเนินการล้มเหลว',
    },
  },
  vi: {
    nav: {
      signals: 'Chợ tín hiệu',
      strategies: 'Chiến lược',
      discussions: 'Thảo luận',
      positions: 'Vị thế',
      trade: 'Giao dịch',
      exchange: 'Trao đổi',
      create: 'Tạo',
    },
    common: {
      login: 'Đăng nhập',
      logout: 'Đăng xuất',
      connected: 'Đã kết nối',
      balance: 'Số dư',
      claw: 'CLAW',
      points: 'điểm',
      loading: 'Đang tải...',
      cancel: 'Hủy',
      confirm: 'Xác nhận',
      submit: 'Gửi',
      close: 'Đóng',
      back: 'Quay lại',
      next: 'Tiếp theo',
      refresh: 'Làm mới',
    },
    signals: {
      operations: 'Thao tác',
      noSignals: 'Chưa có tín hiệu',
      publish: 'Đăng',
    },
    strategies: {
      title: 'Chiến lược',
      market: 'Thị trường',
      noStrategies: 'Chưa có chiến lược',
      publish: 'Đăng chiến lược',
      publishSuccess: 'Đã đăng chiến lược!',
      submit: 'Đăng',
      content: 'Nội dung chiến lược',
      symbols: 'Mã liên quan',
      tags: 'Thẻ',
    },
    discussions: {
      title: 'Thảo luận',
      market: 'Thị trường',
      noDiscussions: 'Chưa có thảo luận',
      post: 'Đăng thảo luận',
      postSuccess: 'Đã đăng thảo luận!',
      submit: 'Đăng',
      content: 'Nội dung thảo luận',
      tags: 'Thẻ',
    },
    positions: {
      title: 'Vị thế của tôi',
      noPositions: 'Chưa có vị thế',
    },
    trade: {
      title: 'Đặt lệnh',
      market: 'Thị trường',
      action: 'Hành động',
      symbol: 'Mã',
      price: 'Giá',
      quantity: 'Số lượng',
      content: 'Ghi chú',
      executedAt: 'Thời gian giao dịch',
      submit: 'Gửi lệnh',
      success: 'Đặt lệnh thành công!',
      buy: 'Mua',
      sell: 'Bán',
      short: 'Bán khống',
      cover: 'Đóng khống',
    },
    exchange: {
      title: 'Đổi điểm',
      currentPoints: 'Điểm hiện tại',
      currentCash: 'Tiền hiện tại',
      exchangeRate: 'Tỉ giá: 1 điểm = 1.000 USD',
      amount: 'Số điểm cần đổi',
      submit: 'Đổi ngay',
      success: 'Đổi thành công!',
      insufficientPoints: 'Không đủ điểm',
      enterAmount: 'Vui lòng nhập số điểm cần đổi',
    },
    login: {
      title: 'Đăng ký / Đăng nhập',
      name: 'Tên',
      email: 'Email',
      register: 'Đăng ký',
      registering: 'Đang đăng ký...',
      success: 'Đăng nhập thành công!',
      failed: 'Đăng nhập thất bại',
    },
    errors: {
      pleaseLogin: 'Vui lòng đăng nhập trước',
      operationFailed: 'Thao tác thất bại',
    },
  },
}

// Get translation function
export const getT = (lang: Language): Translations => translations[lang]

// Inline translation helper for ad-hoc strings outside the structured Translations.
// Usage: tr(language, { en: 'Back', ja: '戻る', th: 'กลับ', vi: 'Quay lại' })
// Falls back to English if a translation is missing.
export type TrMap = { en: string } & Partial<Record<Language, string>>
export const tr = (lang: Language, m: TrMap): string => m[lang] ?? m.en

// Category translations
export const categoryTranslations: Record<Language, Record<string, string>> = {
  en: {
    'trading-signal': 'Trading Signal',
    'data-feed': 'Data Feed',
    'model-access': 'Model Access',
    'analysis': 'Analysis',
    'tool': 'Tool',
    'all': 'All Categories',
  },
  ja: {
    'trading-signal': '取引シグナル',
    'data-feed': 'データフィード',
    'model-access': 'モデルアクセス',
    'analysis': '分析',
    'tool': 'ツール',
    'all': 'すべてのカテゴリ',
  },
  th: {
    'trading-signal': 'สัญญาณเทรด',
    'data-feed': 'แหล่งข้อมูล',
    'model-access': 'เข้าถึงโมเดล',
    'analysis': 'การวิเคราะห์',
    'tool': 'เครื่องมือ',
    'all': 'ทุกหมวดหมู่',
  },
  vi: {
    'trading-signal': 'Tín hiệu giao dịch',
    'data-feed': 'Nguồn dữ liệu',
    'model-access': 'Truy cập mô hình',
    'analysis': 'Phân tích',
    'tool': 'Công cụ',
    'all': 'Tất cả danh mục',
  },
}
