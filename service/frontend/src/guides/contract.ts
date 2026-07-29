import type { PageGuide } from './types'

export const contractGuide: PageGuide = {
  title: {
    ko: '엔터프라이즈 문의',
    en: 'Enterprise — contact us',
    ja: 'エンタープライズ問い合わせ',
    th: 'เอนเทอร์ไพรส์ — ติดต่อเรา',
    vi: 'Enterprise — liên hệ',
    id: 'Enterprise — hubungi kami',
  },
  summary: {
    ko: '팀 규모와 요구사항을 적어 맞춤 계약을 요청하는 한 장짜리 문의 폼입니다. 표준 플랜 대신 엔터프라이즈 계약이 필요한 조직이 사용합니다.',
    en: 'A single-page request form where you describe your team and requirements to ask for a custom contract. Used by organisations that need an enterprise agreement instead of a standard plan.',
    ja: 'チーム規模と要件を記入してカスタム契約を依頼する 1 ページの問い合わせフォームです。標準プランではなくエンタープライズ契約が必要な組織が使います。',
    th: 'ฟอร์มคำขอหน้าเดียวสำหรับอธิบายทีมและความต้องการของคุณเพื่อขอสัญญาแบบกำหนดเอง ใช้โดยองค์กรที่ต้องการข้อตกลงเอนเทอร์ไพรส์แทนแพลนมาตรฐาน',
    vi: 'Biểu mẫu yêu cầu một trang, nơi bạn mô tả đội ngũ và nhu cầu để xin hợp đồng riêng. Dành cho tổ chức cần thỏa thuận enterprise thay vì gói tiêu chuẩn.',
    id: 'Formulir permintaan satu halaman tempat Anda menjelaskan tim dan kebutuhan Anda untuk mengajukan kontrak khusus. Dipakai oleh organisasi yang memerlukan perjanjian enterprise, bukan paket standar.',
  },
  sections: [
    {
      heading: {
        ko: '입력해야 할 항목',
        en: 'What the form asks for',
        ja: '入力する項目',
        th: 'สิ่งที่ฟอร์มต้องการ',
        vi: 'Biểu mẫu yêu cầu những gì',
        id: 'Apa yang diminta formulir ini',
      },
      bullets: {
        ko: [
          '이름과 이메일은 필수입니다. 둘 중 하나라도 비어 있으면 "문의 보내기" 버튼이 눌리지 않습니다.',
          '회사명은 어느 조직에서 보낸 문의인지 구분하는 데 쓰입니다.',
          '전화번호는 라벨에 "(선택)"으로 표시된 대로 비워 두어도 됩니다.',
          '"요구사항"은 여러 줄 입력이 가능한 칸으로, 팀 규모·사용 목적·필요한 지원 범위를 구체적으로 적을수록 회신이 정확해집니다.',
        ],
        en: [
          'Name and email are required — the "Send request" button stays disabled if either is blank.',
          'Company is used to tell which organisation the request came from.',
          'Phone is marked "(optional)" on its label and can be left empty.',
          'The "Requirements" box accepts multiple lines; the more concretely you describe team size, intended use, and the support you need, the more accurate the reply.',
        ],
        ja: [
          '氏名とメールアドレスは必須です。どちらかが空だと「リクエストを送信」ボタンは押せません。',
          '会社名は、どの組織からの問い合わせかを判別するために使われます。',
          '電話番号はラベルに「(任意)」と表示されているとおり、空欄のままで構いません。',
          '「要件」は複数行入力できる欄で、チーム規模・利用目的・必要なサポート範囲を具体的に書くほど回答が正確になります。',
        ],
        th: [
          'ชื่อและอีเมลเป็นข้อมูลบังคับ ถ้าเว้นว่างช่องใดช่องหนึ่ง ปุ่ม "ส่งคำขอ" จะยังกดไม่ได้',
          'ช่องบริษัทใช้ระบุว่าคำขอมาจากองค์กรใด',
          'เบอร์โทรศัพท์ระบุว่า "(ไม่บังคับ)" บนป้ายกำกับ จึงเว้นว่างได้',
          'ช่อง "ความต้องการ" พิมพ์ได้หลายบรรทัด ยิ่งอธิบายขนาดทีม วัตถุประสงค์การใช้งาน และขอบเขตการสนับสนุนที่ต้องการอย่างชัดเจน คำตอบก็ยิ่งตรงจุด',
        ],
        vi: [
          'Tên và email là bắt buộc — nút "Gửi yêu cầu" vẫn bị vô hiệu nếu một trong hai để trống.',
          'Trường công ty dùng để biết yêu cầu đến từ tổ chức nào.',
          'Số điện thoại được ghi "(tuỳ chọn)" trên nhãn nên có thể bỏ trống.',
          'Ô "Yêu cầu" nhận nhiều dòng; bạn mô tả càng cụ thể quy mô đội ngũ, mục đích sử dụng và phạm vi hỗ trợ cần thiết thì phản hồi càng chính xác.',
        ],
        id: [
          'Nama dan email wajib diisi — tombol "Kirim permintaan" tetap nonaktif bila salah satunya kosong.',
          'Perusahaan dipakai untuk mengetahui organisasi mana yang mengajukan permintaan.',
          'Telepon ditandai "(opsional)" pada labelnya dan boleh dikosongkan.',
          'Kotak "Kebutuhan" menerima beberapa baris; makin konkret Anda menjelaskan ukuran tim, rencana penggunaan, dan dukungan yang dibutuhkan, makin tepat jawabannya.',
        ],
      },
    },
    {
      heading: {
        ko: '보내고 나면 일어나는 일',
        en: 'What happens after you send',
        ja: '送信後の流れ',
        th: 'สิ่งที่เกิดขึ้นหลังกดส่ง',
        vi: 'Điều gì xảy ra sau khi gửi',
        id: 'Apa yang terjadi setelah Anda mengirim',
      },
      bullets: {
        ko: [
          '전송에 성공하면 폼이 사라지고 초록색 "접수되었습니다" 확인 카드로 바뀝니다.',
          '확인 카드에는 영업일 기준 1–2일 내에 연락하겠다는 안내가 표시됩니다.',
          '실패하면 버튼 위에 붉은 경고 문구가 서버가 돌려준 메시지 그대로 표시되고, 입력한 내용은 그대로 남아 다시 시도할 수 있습니다.',
          '접수된 문의는 운영진의 관리 콘솔로 전달되어 후속 연락이 진행됩니다.',
        ],
        en: [
          'On success the form is replaced by a green "Request received" confirmation card.',
          'That card states that you will be contacted within 1–2 business days.',
          'On failure a red warning appears above the button carrying the server\'s message verbatim, and your input stays in place so you can retry.',
          'Submitted requests go through to the operators\' management console for follow-up.',
        ],
        ja: [
          '送信に成功するとフォームが消え、緑色の「リクエストを受け付けました」確認カードに切り替わります。',
          'その確認カードには、営業日ベースで 1〜2 日以内に連絡する旨が表示されます。',
          '失敗した場合はボタンの上に赤い警告が表示され、サーバーが返したメッセージがそのまま出ます。入力内容は残るので再試行できます。',
          '受け付けた問い合わせは運営側の管理コンソールに送られ、そこからフォローアップが行われます。',
        ],
        th: [
          'เมื่อส่งสำเร็จ ฟอร์มจะถูกแทนที่ด้วยการ์ดยืนยันสีเขียว "ได้รับคำขอแล้ว"',
          'การ์ดนั้นระบุว่าจะติดต่อกลับภายใน 1–2 วันทำการ',
          'ถ้าล้มเหลว จะมีคำเตือนสีแดงเหนือปุ่มแสดงข้อความจากเซิร์ฟเวอร์ตามตัวอักษร และข้อมูลที่กรอกยังอยู่ให้ลองใหม่ได้',
          'คำขอที่ส่งเข้ามาจะเข้าสู่คอนโซลจัดการของทีมงานเพื่อติดตามต่อ',
        ],
        vi: [
          'Khi gửi thành công, biểu mẫu được thay bằng thẻ xác nhận màu xanh "Đã nhận yêu cầu".',
          'Thẻ đó cho biết bạn sẽ được liên hệ trong vòng 1–2 ngày làm việc.',
          'Khi lỗi, một cảnh báo đỏ hiện phía trên nút với nguyên văn thông báo từ máy chủ, và dữ liệu bạn nhập vẫn còn để thử lại.',
          'Yêu cầu đã gửi sẽ chuyển vào bảng quản trị của đội vận hành để theo dõi tiếp.',
        ],
        id: [
          'Bila berhasil, formulir diganti dengan kartu konfirmasi hijau "Permintaan diterima".',
          'Kartu itu menyatakan bahwa Anda akan dihubungi dalam 1–2 hari kerja.',
          'Bila gagal, peringatan merah muncul di atas tombol memuat pesan dari server apa adanya, dan isian Anda tetap tersimpan sehingga bisa dicoba lagi.',
          'Permintaan yang terkirim diteruskan ke konsol manajemen operator untuk ditindaklanjuti.',
        ],
      },
    },
    {
      heading: {
        ko: '플랜 화면으로 돌아가기',
        en: 'Getting back to the plans',
        ja: 'プラン画面に戻る',
        th: 'กลับไปหน้าแพลน',
        vi: 'Quay lại trang gói',
        id: 'Kembali ke daftar paket',
      },
      bullets: {
        ko: [
          '폼 아래와 접수 완료 카드 안 모두에 "플랜 보기로 돌아가기" 링크가 있어 구독 페이지로 이동합니다.',
          '문의 회신을 기다리는 동안 표준 플랜으로 먼저 시작하고 싶다면 구독 페이지에서 바로 결제할 수 있습니다.',
          '이 페이지는 로그인 없이도 열리지만, 로그인한 상태로 보내면 문의가 해당 계정과 함께 기록됩니다.',
        ],
        en: [
          'A "Back to plans" link sits both below the form and inside the confirmation card, returning you to the subscribe page.',
          'If you would rather start on a standard plan while waiting for a reply, you can pay directly from the subscribe page.',
          'The page opens without signing in, but sending it while signed in records the request together with your account.',
        ],
        ja: [
          'フォームの下と受付完了カードの中の両方に「プラン一覧に戻る」リンクがあり、購読ページへ移動します。',
          '返信を待つ間に標準プランで先に始めたい場合は、購読ページからそのまま支払えます。',
          'このページはログインしなくても開けますが、ログイン状態で送信すると問い合わせがそのアカウントと紐づけて記録されます。',
        ],
        th: [
          'ลิงก์ "กลับไปหน้าแพลน" อยู่ทั้งใต้ฟอร์มและในการ์ดยืนยัน ซึ่งจะพากลับไปหน้าสมัครสมาชิก',
          'ถ้าอยากเริ่มด้วยแพลนมาตรฐานระหว่างรอคำตอบ คุณชำระเงินได้เลยจากหน้าสมัครสมาชิก',
          'หน้านี้เปิดได้โดยไม่ต้องเข้าสู่ระบบ แต่ถ้าส่งขณะเข้าสู่ระบบอยู่ คำขอจะถูกบันทึกพร้อมกับบัญชีของคุณ',
        ],
        vi: [
          'Liên kết "Quay lại các gói" nằm cả bên dưới biểu mẫu lẫn trong thẻ xác nhận, đưa bạn về trang đăng ký.',
          'Nếu muốn bắt đầu bằng gói tiêu chuẩn trong lúc chờ phản hồi, bạn có thể thanh toán ngay ở trang đăng ký.',
          'Trang này mở được mà không cần đăng nhập, nhưng gửi khi đã đăng nhập sẽ ghi nhận yêu cầu kèm tài khoản của bạn.',
        ],
        id: [
          'Tautan "Kembali ke daftar paket" tersedia di bawah formulir maupun di dalam kartu konfirmasi, membawa Anda kembali ke halaman berlangganan.',
          'Jika Anda lebih suka memulai dengan paket standar sambil menunggu jawaban, Anda bisa membayar langsung dari halaman berlangganan.',
          'Halaman ini bisa dibuka tanpa masuk, tetapi mengirimnya sambil sudah masuk akan mencatat permintaan itu bersama akun Anda.',
        ],
      },
    },
  ],
  faq: [
    {
      q: {
        ko: '로그인해야 문의를 보낼 수 있나요?',
        en: 'Do I need to sign in to send a request?',
        ja: '問い合わせを送るにはログインが必要ですか？',
        th: 'ต้องเข้าสู่ระบบก่อนถึงจะส่งคำขอได้ไหม',
        vi: 'Tôi có cần đăng nhập để gửi yêu cầu không?',
        id: 'Apakah saya harus masuk untuk mengirim permintaan?',
      },
      a: {
        ko: '필수는 아닙니다. 이름과 이메일만 채우면 로그인 없이도 보낼 수 있습니다. 다만 로그인한 상태로 보내면 문의가 계정 정보와 함께 전달되어 후속 처리가 수월합니다.',
        en: 'Not required. With a name and email filled in you can send it without signing in. Sending while signed in does attach your account information, which makes follow-up easier.',
        ja: '必須ではありません。氏名とメールを入力すればログインなしで送信できます。ただしログイン状態で送るとアカウント情報が添付され、その後の対応がスムーズになります。',
        th: 'ไม่จำเป็น เพียงกรอกชื่อและอีเมลก็ส่งได้โดยไม่ต้องเข้าสู่ระบบ แต่ถ้าส่งขณะเข้าสู่ระบบอยู่ ข้อมูลบัญชีจะแนบไปด้วยทำให้ติดตามงานง่ายขึ้น',
        vi: 'Không bắt buộc. Chỉ cần điền tên và email là gửi được mà không cần đăng nhập. Tuy nhiên gửi khi đã đăng nhập sẽ đính kèm thông tin tài khoản, giúp việc theo dõi dễ hơn.',
        id: 'Tidak wajib. Dengan nama dan email terisi, Anda bisa mengirimnya tanpa masuk. Mengirim sambil sudah masuk memang melampirkan informasi akun Anda, yang mempermudah tindak lanjut.',
      },
    },
    {
      q: {
        ko: '버튼이 회색이라 눌리지 않습니다.',
        en: 'The button is greyed out and will not click.',
        ja: 'ボタンがグレーで押せません。',
        th: 'ปุ่มเป็นสีเทาและกดไม่ได้',
        vi: 'Nút bị xám và không nhấn được.',
        id: 'Tombolnya berwarna abu-abu dan tidak bisa diklik.',
      },
      a: {
        ko: '이름과 이메일 두 칸이 모두 채워져야 버튼이 활성화됩니다. 전송 중에도 잠시 비활성 상태가 되니, 공백만 입력하지 않았는지 확인해 보세요.',
        en: 'The button only enables once both the name and email fields contain text. It is also disabled briefly while sending, so check you have not entered only whitespace.',
        ja: '氏名とメールの両方が入力されて初めてボタンが有効になります。送信中も一時的に無効になるため、空白だけを入力していないか確認してください。',
        th: 'ปุ่มจะกดได้เมื่อกรอกทั้งช่องชื่อและอีเมลแล้วเท่านั้น และจะถูกปิดชั่วคราวระหว่างกำลังส่งด้วย ลองตรวจว่าไม่ได้พิมพ์เพียงช่องว่าง',
        vi: 'Nút chỉ bật khi cả ô tên lẫn email đều có nội dung. Nó cũng bị tắt trong lúc đang gửi, nên hãy kiểm tra bạn không chỉ nhập khoảng trắng.',
        id: 'Tombolnya baru aktif setelah kolom nama dan email terisi teks. Tombol itu juga nonaktif sesaat selama pengiriman, jadi pastikan Anda tidak hanya memasukkan spasi.',
      },
    },
    {
      q: {
        ko: '여기서 가격 견적을 바로 볼 수 있나요?',
        en: 'Can I see a price quote right here?',
        ja: 'ここで見積もりをすぐ確認できますか？',
        th: 'ดูใบเสนอราคาได้ทันทีที่นี่ไหม',
        vi: 'Tôi có thể xem báo giá ngay tại đây không?',
        id: 'Bisakah saya melihat penawaran harga langsung di sini?',
      },
      a: {
        ko: '아니요. 이 페이지는 요청을 접수하기만 하고 금액을 계산하거나 표시하지 않습니다. 조건은 담당자가 회신하면서 안내합니다. 공개된 월 정액 플랜 금액은 구독 페이지에서 확인하세요.',
        en: 'No. This page only files the request; it does not calculate or display any figures. Terms come back with the reply. Published monthly plan prices are on the subscribe page.',
        ja: 'いいえ。このページはリクエストを受け付けるだけで、金額を計算・表示することはありません。条件は担当者からの返信でご案内します。公開されている月額プランの金額は購読ページで確認してください。',
        th: 'ไม่ได้ หน้านี้เพียงรับคำขอเท่านั้น ไม่ได้คำนวณหรือแสดงตัวเลขใด ๆ เงื่อนไขจะแจ้งกลับมาพร้อมคำตอบ ส่วนราคาแพลนรายเดือนที่ประกาศไว้ดูได้ที่หน้าสมัครสมาชิก',
        vi: 'Không. Trang này chỉ ghi nhận yêu cầu; nó không tính hay hiển thị con số nào. Điều khoản sẽ được gửi kèm phản hồi. Giá các gói hàng tháng đã công bố nằm ở trang đăng ký.',
        id: 'Tidak. Halaman ini hanya mencatat permintaan; ia tidak menghitung atau menampilkan angka apa pun. Ketentuannya datang bersama jawaban kami. Harga paket bulanan yang dipublikasikan ada di halaman berlangganan.',
      },
    },
  ],
}
