from pathlib import Path
import re

FILES = {
    'client': Path('Client.html'),
    'photo': Path('HousemanRequestPhotoClient.html'),
}
texts = {key: path.read_text(encoding='utf-8') for key, path in FILES.items()}
originals = dict(texts)


def replace_once(key, old, new, label):
    count = texts[key].count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    texts[key] = texts[key].replace(old, new, 1)


# -----------------------------------------------------------------------------
# Client.html: if native camera causes the Apps Script iframe/tab to be recreated,
# restore the roommaid cleaning menu from a short-lived photo resume context.
# -----------------------------------------------------------------------------
replace_once(
    'client',
    "    activeMenu: sessionStorage.getItem('novaActiveMenu') || '',\n",
    """    activeMenu: (() => {\n      const savedMenu = sessionStorage.getItem('novaActiveMenu') || '';\n      try {\n        const resume = JSON.parse(localStorage.getItem('novaHmRequestPhotoResume') || '{}');\n        const savedAt = Number(resume && resume.savedAt || 0);\n        if (resume && resume.roomNo && savedAt && Date.now() - savedAt <= 5 * 60 * 1000) return 'cleaning';\n      } catch (ignore) {}\n      return savedMenu;\n    })(),\n""",
    'camera resume active menu fallback'
)

# -----------------------------------------------------------------------------
# HousemanRequestPhotoClient.html: explicit camera button, resume context,
# lifecycle recovery, and lower-memory object-URL photo decode.
# -----------------------------------------------------------------------------
replace_once(
    'photo',
    """  const PHOTO_PREVIEW_LIST_ID = 'novaHmRequestPhotoPreviewList';\n  const MAX_PHOTO_BYTES = 2500000;\n  const DEFAULT_MAX_PHOTOS_PER_ORDER = 5;\n""",
    """  const PHOTO_PREVIEW_LIST_ID = 'novaHmRequestPhotoPreviewList';\n  const PHOTO_RESUME_KEY = 'novaHmRequestPhotoResume';\n  const PHOTO_RESUME_TTL_MS = 5 * 60 * 1000;\n  const MAX_PHOTO_BYTES = 2500000;\n  const DEFAULT_MAX_PHOTOS_PER_ORDER = 5;\n""",
    'photo resume constants'
)

replace_once(
    'photo',
    """  let capabilityPromise = null;\n  let toastTimer = null;\n\n  document.addEventListener('click', handleHousemanPhotoClickCapture_, true); // (룸메이드 요청사진 클릭 선처리)\n""",
    """  let capabilityPromise = null;\n  let toastTimer = null;\n  let nativeCapturePending = false;\n  let nativeCaptureReturnTimer = null;\n\n  document.addEventListener('click', handleHousemanPhotoClickCapture_, true); // (룸메이드 요청사진 클릭 선처리)\n  document.addEventListener('visibilitychange', handleHousemanPhotoVisibilityChange_); // (기기 카메라 취소·복귀 감지)\n  window.setTimeout(restoreHousemanPhotoRequestAfterReload_, 250); // (카메라 중 페이지 재생성 시 요청창 복원)\n""",
    'photo lifecycle hooks'
)

replace_once(
    'photo',
    """      <div class=\"nova-hm-photo-actions\">\n        <label id=\"${PHOTO_CAMERA_ID}\" class=\"nova-hm-photo-camera\" for=\"${PHOTO_INPUT_ID}\">사진 촬영</label>\n        <input id=\"${PHOTO_INPUT_ID}\" class=\"nova-hm-photo-input\" type=\"file\" accept=\"image/*\" capture=\"environment\">\n      </div>\n""",
    """      <div class=\"nova-hm-photo-actions\">\n        <button id=\"${PHOTO_CAMERA_ID}\" class=\"nova-hm-photo-camera\" type=\"button\">사진 촬영</button>\n        <input id=\"${PHOTO_INPUT_ID}\" class=\"nova-hm-photo-input\" type=\"file\" accept=\"image/*\" capture=\"environment\">\n      </div>\n""",
    'explicit camera button'
)

replace_once(
    'photo',
    """    const input = document.getElementById(PHOTO_INPUT_ID);\n    const previewList = document.getElementById(PHOTO_PREVIEW_LIST_ID);\n    if (input) input.addEventListener('change', handleHousemanPhotoSelection_);\n    if (previewList) previewList.addEventListener('click', handleHousemanPhotoRemoveClick_);\n    renderHousemanPhotoPreviews_();\n  }\n\n  function getHousemanPhotoCapability_(token) { // (현재 토큰의 룸메이드 사진기능 권한 조회·세션 캐시)\n""",
    """    const input = document.getElementById(PHOTO_INPUT_ID);\n    const camera = document.getElementById(PHOTO_CAMERA_ID);\n    const previewList = document.getElementById(PHOTO_PREVIEW_LIST_ID);\n    if (input) input.addEventListener('change', handleHousemanPhotoSelection_);\n    if (camera) camera.addEventListener('click', handleHousemanPhotoCameraClick_);\n    if (previewList) previewList.addEventListener('click', handleHousemanPhotoRemoveClick_);\n    renderHousemanPhotoPreviews_();\n  }\n\n  function readHousemanPhotoResumeContext_() { // (카메라 복귀용 임시 요청내용 조회)\n    try {\n      const context = JSON.parse(localStorage.getItem(PHOTO_RESUME_KEY) || 'null');\n      if (!context || !context.roomNo || !Number(context.savedAt || 0)) return null;\n      if (Date.now() - Number(context.savedAt || 0) > PHOTO_RESUME_TTL_MS) {\n        localStorage.removeItem(PHOTO_RESUME_KEY);\n        return null;\n      }\n      return context;\n    } catch (ignore) {\n      localStorage.removeItem(PHOTO_RESUME_KEY);\n      return null;\n    }\n  }\n\n  function persistHousemanPhotoResumeContext_() { // (기기 카메라 실행 직전 요청화면·입력값 보존)\n    if (!activeRoomNo) return;\n    const context = {\n      savedAt: Date.now(),\n      roomNo: activeRoomNo,\n      part: String(document.getElementById('mobileRequestPart')?.value || ''),\n      item: String(document.getElementById('mobileRequestItem')?.value || ''),\n      quantity: String(document.getElementById('mobileRequestQty')?.value || '1'),\n      note: String(document.getElementById('mobileRequestNote')?.value || ''),\n      businessDate: String(document.getElementById('mobileDate')?.value || ''),\n      site: String(document.getElementById('mobileSite')?.value || '')\n    };\n    try {\n      localStorage.setItem(PHOTO_RESUME_KEY, JSON.stringify(context));\n      sessionStorage.setItem('novaActiveMenu', 'cleaning');\n    } catch (ignore) {}\n  }\n\n  function clearHousemanPhotoResumeContext_() { // (카메라 복귀 임시정보 정리)\n    try { localStorage.removeItem(PHOTO_RESUME_KEY); } catch (ignore) {}\n  }\n\n  function handleHousemanPhotoCameraClick_(event) { // (요청내용 보존 후 기기 후면카메라 실행)\n    event.preventDefault();\n    const camera = event.currentTarget;\n    if (!camera || camera.classList.contains('disabled') || camera.getAttribute('aria-disabled') === 'true') return;\n    const input = document.getElementById(PHOTO_INPUT_ID);\n    if (!input || input.disabled) return;\n    persistHousemanPhotoResumeContext_();\n    nativeCapturePending = true;\n    input.click();\n  }\n\n  function handleHousemanPhotoVisibilityChange_() { // (사진촬영 취소 시 오래된 복원정보 제거)\n    if (document.hidden || !nativeCapturePending) return;\n    if (nativeCaptureReturnTimer) window.clearTimeout(nativeCaptureReturnTimer);\n    nativeCaptureReturnTimer = window.setTimeout(() => {\n      if (!nativeCapturePending) return;\n      const input = document.getElementById(PHOTO_INPUT_ID);\n      if (!input || !input.files || !input.files.length) {\n        nativeCapturePending = false;\n        clearHousemanPhotoResumeContext_();\n      }\n    }, 1400);\n  }\n\n  function restoreHousemanPhotoRequestAfterReload_() { // (카메라 복귀 중 WebView 재생성 시 같은 요청창 자동 복원)\n    const context = readHousemanPhotoResumeContext_();\n    if (!context) return;\n    try { sessionStorage.setItem('novaActiveMenu', 'cleaning'); } catch (ignore) {}\n    const startedAt = Date.now();\n\n    const tryRestore = () => {\n      if (Date.now() - startedAt > 20000) {\n        clearHousemanPhotoResumeContext_();\n        return;\n      }\n\n      let submit = document.getElementById('mobileRequestSubmit');\n      if (!submit) {\n        const requestButton = Array.from(document.querySelectorAll('[data-houseman-request]'))\n          .find(button => String(button.dataset.housemanRequest || '').trim() === String(context.roomNo || '').trim());\n        if (requestButton) {\n          requestButton.click();\n          window.setTimeout(tryRestore, 160);\n          return;\n        }\n        window.setTimeout(tryRestore, 260);\n        return;\n      }\n\n      activeRoomNo = String(context.roomNo || '').trim();\n      const part = document.getElementById('mobileRequestPart');\n      const item = document.getElementById('mobileRequestItem');\n      const quantity = document.getElementById('mobileRequestQty');\n      const note = document.getElementById('mobileRequestNote');\n      if (part && context.part) part.value = String(context.part);\n      if (item) item.value = String(context.item || '');\n      if (quantity) quantity.value = String(context.quantity || '1');\n      if (note) note.value = String(context.note || '');\n\n      Promise.resolve(prepareHousemanPhotoUi_(activeRoomNo)).finally(() => {\n        window.setTimeout(() => {\n          setHousemanPhotoStatus_('카메라 복귀 후 요청내용을 복원했습니다. 사진을 다시 촬영해 주세요.', '');\n        }, 80);\n      });\n      clearHousemanPhotoResumeContext_();\n    };\n\n    tryRestore();\n  }\n\n  function getHousemanPhotoCapability_(token) { // (현재 토큰의 룸메이드 사진기능 권한 조회·세션 캐시)\n""",
    'photo camera resume helpers'
)

replace_once(
    'photo',
    """  async function handleHousemanPhotoSelection_(event) { // (촬영 사진을 최대 5장까지 순차 압축·추가)\n    const input = event.currentTarget;\n    const file = input && input.files && input.files[0];\n    if (input) input.value = ''; // 같은 사진을 다시 선택해도 change가 동작하도록 즉시 초기화\n    if (!file) return;\n""",
    """  async function handleHousemanPhotoSelection_(event) { // (촬영 사진을 최대 5장까지 순차 압축·추가)\n    const input = event.currentTarget;\n    const file = input && input.files && input.files[0];\n    nativeCapturePending = false;\n    if (nativeCaptureReturnTimer) window.clearTimeout(nativeCaptureReturnTimer);\n    nativeCaptureReturnTimer = null;\n    if (input) input.value = ''; // 같은 사진을 다시 선택해도 change가 동작하도록 초기화\n    if (!file) {\n      clearHousemanPhotoResumeContext_();\n      return;\n    }\n""",
    'photo selection lifecycle reset'
)

replace_once(
    'photo',
    """    await photoPreparePromise;\n  }\n\n  function handleHousemanPhotoRemoveClick_(event) { // (선택 사진 개별 삭제)\n""",
    """    await photoPreparePromise;\n    clearHousemanPhotoResumeContext_();\n  }\n\n  function handleHousemanPhotoRemoveClick_(event) { // (선택 사진 개별 삭제)\n""",
    'clear resume after photo preparation'
)

old_compress = """  async function compressHousemanRequestPhoto_(file) { // (요청사진 1600px JPEG 압축)\n    if (!file || !String(file.type || '').startsWith('image/')) throw new Error('이미지 파일만 등록할 수 있습니다.');\n    const dataUrl = await new Promise((resolve, reject) => {\n      const reader = new FileReader();\n      reader.onload = () => resolve(reader.result);\n      reader.onerror = () => reject(new Error('사진을 읽지 못했습니다.'));\n      reader.readAsDataURL(file);\n    });\n    const image = await new Promise((resolve, reject) => {\n      const img = new Image();\n      img.onload = () => resolve(img);\n      img.onerror = () => reject(new Error('지원하지 않는 사진 형식입니다.'));\n      img.src = dataUrl;\n    });\n    const max = 1600;\n    const scale = Math.min(1, max / Math.max(image.naturalWidth, image.naturalHeight));\n    const canvas = document.createElement('canvas');\n    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));\n    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));\n    const context = canvas.getContext('2d');\n    if (!context) throw new Error('사진 압축을 시작하지 못했습니다.');\n    context.drawImage(image, 0, 0, canvas.width, canvas.height);\n    const compressed = canvas.toDataURL('image/jpeg', 0.78);\n    const base64 = compressed.split(',')[1] || '';\n    const byteSize = Math.ceil(base64.length * 0.75);\n    if (!base64 || byteSize > MAX_PHOTO_BYTES) throw new Error('사진 용량이 큽니다. 더 낮은 해상도로 촬영해 주세요.');\n    const sourceName = String(file.name || 'houseman-request').replace(/\\.[^.]+$/, '') || 'houseman-request';\n    return { fileName: `${sourceName}.jpg`, mimeType: 'image/jpeg', base64, byteSize };\n  }\n"""
new_compress = """  async function compressHousemanRequestPhoto_(file) { // (요청사진 1600px JPEG 압축·원본 Base64 복제 방지)\n    if (!file || !String(file.type || '').startsWith('image/')) throw new Error('이미지 파일만 등록할 수 있습니다.');\n    if (!window.URL || typeof window.URL.createObjectURL !== 'function') throw new Error('현재 브라우저에서 사진을 처리할 수 없습니다.');\n\n    const objectUrl = window.URL.createObjectURL(file);\n    let image = null;\n    let canvas = null;\n    try {\n      image = await new Promise((resolve, reject) => {\n        const img = new Image();\n        img.decoding = 'async';\n        img.onload = () => resolve(img);\n        img.onerror = () => reject(new Error('지원하지 않는 사진 형식입니다.'));\n        img.src = objectUrl;\n      });\n      const max = 1600;\n      const scale = Math.min(1, max / Math.max(image.naturalWidth, image.naturalHeight));\n      canvas = document.createElement('canvas');\n      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));\n      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));\n      const context = canvas.getContext('2d', { alpha: false });\n      if (!context) throw new Error('사진 압축을 시작하지 못했습니다.');\n      context.drawImage(image, 0, 0, canvas.width, canvas.height);\n      const compressed = canvas.toDataURL('image/jpeg', 0.78);\n      const base64 = compressed.split(',')[1] || '';\n      const byteSize = Math.ceil(base64.length * 0.75);\n      if (!base64 || byteSize > MAX_PHOTO_BYTES) throw new Error('사진 용량이 큽니다. 더 낮은 해상도로 촬영해 주세요.');\n      const sourceName = String(file.name || 'houseman-request').replace(/\\.[^.]+$/, '') || 'houseman-request';\n      return { fileName: `${sourceName}.jpg`, mimeType: 'image/jpeg', base64, byteSize };\n    } finally {\n      try { if (image) image.src = ''; } catch (ignore) {}\n      try { if (canvas) { canvas.width = 1; canvas.height = 1; } } catch (ignore) {}\n      try { window.URL.revokeObjectURL(objectUrl); } catch (ignore) {}\n    }\n  }\n"""
replace_once('photo', old_compress, new_compress, 'lower memory photo compression')

# write only intended files
for key, path in FILES.items():
    if texts[key] == originals[key]:
        raise SystemExit(f'PATCH_ERROR: no change produced for {path}')
    path.write_text(texts[key], encoding='utf-8')

# targeted validation
client = texts['client']
photo = texts['photo']
checks = [
    ('client resume context', "localStorage.getItem('novaHmRequestPhotoResume')" in client),
    ('cleaning restore priority', "return 'cleaning';" in client),
    ('explicit camera button', f'id=\\"${{PHOTO_CAMERA_ID}}\\" class=\\"nova-hm-photo-camera\\" type=\\"button\\"' in photo),
    ('resume persistence', 'persistHousemanPhotoResumeContext_' in photo),
    ('reload restoration', 'restoreHousemanPhotoRequestAfterReload_' in photo),
    ('native cancel cleanup', 'handleHousemanPhotoVisibilityChange_' in photo),
    ('object url compression', 'URL.createObjectURL(file)' in photo and 'reader.readAsDataURL(file)' not in photo),
    ('existing fast submit kept', 'submitHousemanRequestWithPhotos_' in photo and 'novaCreateRoommaidHousemanRequestFast_' in photo),
    ('photo upload kept', 'uploadMobileHousemanRequestPhoto' in photo),
]
failed = [name for name, ok in checks if not ok]
if failed:
    raise SystemExit('PATCH_ERROR: validation failed: ' + ', '.join(failed))

print('HOUSEMAN_PHOTO_CAMERA_RESUME_V68_OK')
print('Changed: Client.html, HousemanRequestPhotoClient.html only')
print('Camera: existing capture=environment preserved')
print('Recovery: cleaning menu + same room request form restored after WebView/page recreation')
print('Memory: original photo FileReader base64 copy removed; object URL decode used')
print('Existing Realtime create/photo upload/monthly viewer paths preserved')
