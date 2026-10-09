// admin-js/content.js: Контакты, оплата, места, акции, фото и медиа, вкладки настроек, арендодатель, отзывы, правила проживания.
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.
// CONTACTS ADMIN
async function loadContacts() {
  try {
    const c = await apiGet('/api/contacts');
    document.getElementById('contactsPhone').value    = c.phone    || '';
    document.getElementById('contactsEmail').value    = c.email    || '';
    document.getElementById('contactsTelegram').value = c.telegram || '';
    document.getElementById('contactsWhatsapp').value = c.whatsapp || '';
    document.getElementById('contactsMax').value      = c.max      || '';
  } catch(e) {}
  loadPaymentSettings();
}

async function saveContacts() {
  const payload = {
    phone:    document.getElementById('contactsPhone').value.trim(),
    email:    document.getElementById('contactsEmail').value.trim(),
    telegram: document.getElementById('contactsTelegram').value.trim().replace(/^@/, ''),
    whatsapp: document.getElementById('contactsWhatsapp').value.trim(),
    max:      document.getElementById('contactsMax').value.trim(),
  };
  try {
    await apiPost('/api/contacts', payload);
    showToast('Контакты сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

// PAYMENT SETTINGS (СБП: ссылка, телефон, свой QR-код)
async function loadPaymentSettings() {
  try {
    const p = await apiGet('/api/payment-settings');
    document.getElementById('paySbpLink').value  = p.sbp_link  || '';
    document.getElementById('paySbpPhone').value = p.sbp_phone || '';
    const preview = document.getElementById('paymentQrPreview');
    const delBtn = document.getElementById('paymentQrDeleteBtn');
    if (p.qr_uploaded) {
      preview.src = '/api/payment-qr?t=' + Date.now();
      preview.style.display = 'block';
      delBtn.style.display = 'inline-block';
    } else {
      preview.style.display = 'none';
      delBtn.style.display = 'none';
    }
  } catch(e) {}
}

async function savePaymentSettings() {
  const payload = {
    sbp_link:  document.getElementById('paySbpLink').value.trim(),
    sbp_phone: document.getElementById('paySbpPhone').value.trim(),
  };
  try {
    await apiPost('/api/payment-settings', payload);
    showToast('Настройки оплаты сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения', 'err');
  }
}

async function uploadPaymentQr(input) {
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch(`${API_BASE}/api/payment-qr`, {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + ADMIN_TOKEN },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Ошибка загрузки');
    showToast('QR-код загружен', 'gold');
    loadPaymentSettings();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
  input.value = '';
}

async function deletePaymentQr() {
  try {
    await fetch(`${API_BASE}/api/payment-qr`, {
      method: 'DELETE',
      headers: { 'Authorization': 'Bearer ' + ADMIN_TOKEN },
    });
    showToast('QR-код удалён', 'gold');
    loadPaymentSettings();
  } catch(e) {
    showToast('Ошибка удаления', 'err');
  }
}

// PLACES ADMIN
let allPlacesAdmin = [];

async function loadPlacesAdmin() {
  try {
    allPlacesAdmin = await apiGet('/api/places/all');
    renderPlacesAdmin(allPlacesAdmin);
  } catch(e) {
    document.getElementById('placesList').innerHTML = '<div style="color:var(--text-muted);padding:20px">Ошибка загрузки</div>';
  }
}

function renderPlacesAdmin(places) {
  const list = document.getElementById('placesList');
  if(!places || places.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Мест пока нет — нажмите «+ Добавить место»</div>';
    return;
  }
  list.innerHTML = places.map(p => `
    <div class="place-row" style="display:grid;grid-template-columns:120px 1fr auto;gap:16px;align-items:center;padding:16px;border:1px solid ${p.visible ? 'var(--black-border)' : 'rgba(90,74,48,.3)'};margin-bottom:8px;background:var(--black-card)">
      <div class="place-row-photo" style="height:80px;overflow:hidden;border:1px solid var(--black-border)">
        ${p.photo ? `<img src="${API_BASE}/data/photos/${p.photo}" style="width:100%;height:100%;object-fit:cover">` : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:24px;background:var(--black)">📍</div>'}
      </div>
      <div style="min-width:0">
        <div style="font-size:10px;color:var(--gold);letter-spacing:.15em;margin-bottom:4px">${p.category || '—'}</div>
        <div style="font-size:14px;color:var(--text-primary);margin-bottom:4px">${p.name}</div>
        <div style="font-size:11px;color:var(--text-muted)">${p.distance || ''}</div>
        ${!p.visible ? '<span style="font-size:10px;color:var(--text-muted);background:rgba(90,74,48,.3);padding:2px 8px">скрыто</span>' : ''}
      </div>
      <div class="place-row-actions" style="display:flex;flex-direction:column;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="editPlace('${p.id}')">✎</button>
        <button class="btn btn-ghost btn-sm" onclick="togglePlaceVisibility('${p.id}', ${!p.visible})">${p.visible ? '👁' : '👁‍🗨'}</button>
        <button class="btn btn-danger btn-sm" onclick="deletePlace('${p.id}')">✕</button>
      </div>
    </div>
  `).join('');
}

function showPlaceForm() {
  document.getElementById('placeEditId').value = '';
  document.getElementById('placeName').value = '';
  document.getElementById('placeCategory').value = '';
  document.getElementById('placeDistance').value = '';
  document.getElementById('placeDescription').value = '';
  document.getElementById('placePhotoValue').value = '';
  document.getElementById('placePhotoName').textContent = 'не выбрано';
  document.getElementById('placePhotoPreview').style.display = 'none';
  document.getElementById('placeFormTitle').textContent = 'Новое место';
  document.getElementById('placeFormWrap').style.display = 'block';
}

function editPlace(id) {
  const p = allPlacesAdmin.find(x => x.id === id);
  if(!p) return;
  document.getElementById('placeEditId').value = p.id;
  document.getElementById('placeName').value = p.name || '';
  document.getElementById('placeCategory').value = p.category || '';
  document.getElementById('placeDistance').value = p.distance || '';
  document.getElementById('placeDescription').value = p.description || '';
  document.getElementById('placePhotoValue').value = p.photo || '';
  if(p.photo) {
    const img = document.getElementById('placePhotoPreview');
    img.src = `${API_BASE}/data/photos/${p.photo}`;
    img.style.display = 'block';
    document.getElementById('placePhotoName').textContent = p.photo;
  }
  document.getElementById('placeFormTitle').textContent = 'Редактировать место';
  document.getElementById('placeFormWrap').style.display = 'block';
}

function cancelPlaceForm() {
  document.getElementById('placeFormWrap').style.display = 'none';
}

async function uploadPlacePhoto() {
  const file = document.getElementById('placePhotoFile').files[0];
  if(!file) return;
  if(file.size > 10 * 1024 * 1024) { showToast('Файл слишком большой (макс. 10 МБ)', 'err'); return; }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', document.getElementById('placeName').value || 'Место');
  formData.append('purpose', 'place');
  try {
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    const data = await resp.json();
    document.getElementById('placePhotoValue').value = data.filename;
    document.getElementById('placePhotoName').textContent = data.filename;
    const img = document.getElementById('placePhotoPreview');
    img.src = `${API_BASE}/data/photos/${data.filename}`;
    img.style.display = 'block';
    showToast('Фото загружено', 'gold');
  } catch(e) { showToast('Ошибка загрузки фото', 'err'); }
}

async function savePlace() {
  const id = document.getElementById('placeEditId').value;
  const payload = {
    name:        document.getElementById('placeName').value.trim(),
    category:    document.getElementById('placeCategory').value.trim(),
    distance:    document.getElementById('placeDistance').value.trim(),
    description: document.getElementById('placeDescription').value.trim(),
    photo:       document.getElementById('placePhotoValue').value.trim(),
    visible:     true
  };
  { const cur = id ? allPlacesAdmin.find(x => x.id === id) : null; if(cur) payload.photo = cur.photo || ''; }
  if(!payload.name) { showToast('Введите название места', 'err'); return; }
  try {
    if(id) await apiPut('/api/places/' + id, payload);
    else   await apiPost('/api/places', payload);
    showToast('Место сохранено', 'gold');
    document.getElementById('placeFormWrap').style.display = 'none';
    loadPlacesAdmin();
  } catch(e) { showToast('Ошибка: ' + e.message, 'err'); }
}

async function togglePlaceVisibility(id, visible) {
  const p = allPlacesAdmin.find(x => x.id === id);
  if(!p) return;
  try {
    await apiPut('/api/places/' + id, {...p, visible});
    showToast(visible ? 'Место показано' : 'Место скрыто', 'gold');
    loadPlacesAdmin();
  } catch(e) { showToast('Ошибка', 'err'); }
}

async function deletePlace(id) {
  if(!confirm('Удалить это место?')) return;
  try {
    await fetch(`${API_BASE}/api/places/${id}`, {
      method: 'DELETE',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    showToast('Место удалено', 'err');
    loadPlacesAdmin();
  } catch(e) { showToast('Ошибка удаления', 'err'); }
}

// DISCOUNTS ADMIN (Скидки и акции)
let allDiscountsAdmin = [];

async function loadDiscountsAdmin() {
  try {
    allDiscountsAdmin = await apiGet('/api/discounts/all');
    renderDiscountsAdmin(allDiscountsAdmin);
  } catch(e) {
    document.getElementById('discountsList').innerHTML = '<div style="color:var(--text-muted);padding:20px">Ошибка загрузки</div>';
  }
}

function renderDiscountsAdmin(discounts) {
  const list = document.getElementById('discountsList');
  if(!discounts || discounts.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Акций пока нет — нажмите «+ Добавить акцию»</div>';
    return;
  }
  list.innerHTML = discounts.map(d => `
    <div class="place-row" style="display:grid;grid-template-columns:120px 1fr auto;gap:16px;align-items:center;padding:16px;border:1px solid ${d.visible ? 'var(--black-border)' : 'rgba(90,74,48,.3)'};margin-bottom:8px;background:var(--black-card)">
      <div class="place-row-photo" style="height:80px;overflow:hidden;border:1px solid var(--black-border)">
        ${d.photo ? `<img src="${API_BASE}/data/photos/${d.photo}" style="width:100%;height:100%;object-fit:cover">` : '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:24px;background:var(--black)">🏷️</div>'}
      </div>
      <div style="min-width:0">
        <div style="font-size:14px;color:var(--text-primary);margin-bottom:4px">${d.name}</div>
        <div style="font-size:11px;color:var(--text-muted)">${(d.description || '').slice(0, 80)}</div>
        ${!d.visible ? '<span style="font-size:10px;color:var(--text-muted);background:rgba(90,74,48,.3);padding:2px 8px">скрыто</span>' : ''}
      </div>
      <div class="place-row-actions" style="display:flex;flex-direction:column;gap:6px">
        <button class="btn btn-ghost btn-sm" onclick="editDiscount('${d.id}')">✎</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleDiscountVisibility('${d.id}', ${!d.visible})">${d.visible ? '👁' : '👁‍🗨'}</button>
        <button class="btn btn-danger btn-sm" onclick="deleteDiscount('${d.id}')">✕</button>
      </div>
    </div>
  `).join('');
}

function showDiscountForm() {
  document.getElementById('discountEditId').value = '';
  document.getElementById('discountName').value = '';
  document.getElementById('discountDescription').value = '';
  document.getElementById('discountPhotoValue').value = '';
  document.getElementById('discountPhotoName').textContent = 'не выбрано';
  document.getElementById('discountPhotoPreview').style.display = 'none';
  document.getElementById('discountPhotoMobileValue').value = '';
  document.getElementById('discountPhotoMobileName').textContent = 'не выбрано';
  document.getElementById('discountPhotoMobilePreview').style.display = 'none';
  document.getElementById('discountFormTitle').textContent = 'Новая акция';
  document.getElementById('discountFormWrap').style.display = 'block';
}

function editDiscount(id) {
  const d = allDiscountsAdmin.find(x => x.id === id);
  if(!d) return;
  document.getElementById('discountEditId').value = d.id;
  document.getElementById('discountName').value = d.name || '';
  document.getElementById('discountDescription').value = d.description || '';
  document.getElementById('discountPhotoValue').value = d.photo || '';
  document.getElementById('discountPhotoMobileValue').value = d.photo_mobile || '';
  document.getElementById('discountPhotoMobileName').textContent = d.photo_mobile || 'не выбрано';
  document.getElementById('discountPhotoMobilePreview').style.display = d.photo_mobile ? 'block' : 'none';
  if(d.photo) {
    const img = document.getElementById('discountPhotoPreview');
    img.src = `${API_BASE}/data/photos/${d.photo}`;
    img.style.display = 'block';
    document.getElementById('discountPhotoName').textContent = d.photo;
  }
  if(d.photo_mobile) {
    document.getElementById('discountPhotoMobilePreview').src = `${API_BASE}/data/photos/${d.photo_mobile}`;
  }
  document.getElementById('discountFormTitle').textContent = 'Редактировать акцию';
  document.getElementById('discountFormWrap').style.display = 'block';
}

function cancelDiscountForm() {
  document.getElementById('discountFormWrap').style.display = 'none';
}

async function uploadDiscountPhoto(variant) {
  const isMobile = variant === 'mobile';
  const fileInputId = isMobile ? 'discountPhotoMobileFile' : 'discountPhotoFile';
  const valueId      = isMobile ? 'discountPhotoMobileValue' : 'discountPhotoValue';
  const nameId       = isMobile ? 'discountPhotoMobileName'  : 'discountPhotoName';
  const previewId    = isMobile ? 'discountPhotoMobilePreview' : 'discountPhotoPreview';
  const file = document.getElementById(fileInputId).files[0];
  if(!file) return;
  if(file.size > 10 * 1024 * 1024) { showToast('Файл слишком большой (макс. 10 МБ)', 'err'); return; }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', document.getElementById('discountName').value || 'Акция');
  formData.append('purpose', 'discount');
  try {
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    const data = await resp.json();
    document.getElementById(valueId).value = data.filename;
    document.getElementById(nameId).textContent = data.filename;
    const img = document.getElementById(previewId);
    img.src = `${API_BASE}/data/photos/${data.filename}`;
    img.style.display = 'block';
    showToast('Фото загружено', 'gold');
  } catch(e) { showToast('Ошибка загрузки фото', 'err'); }
}

async function saveDiscount() {
  const id = document.getElementById('discountEditId').value;
  const payload = {
    name:        document.getElementById('discountName').value.trim(),
    description: document.getElementById('discountDescription').value.trim(),
    photo:       document.getElementById('discountPhotoValue').value.trim(),
    photo_mobile: document.getElementById('discountPhotoMobileValue').value.trim(),
    visible:     true
  };
  { const cur = id ? allDiscountsAdmin.find(x => x.id === id) : null; if(cur) { payload.photo = cur.photo || ''; payload.photo_mobile = cur.photo_mobile || ''; } }
  if(!payload.name) { showToast('Введите название акции', 'err'); return; }
  try {
    if(id) await apiPut('/api/discounts/' + id, payload);
    else   await apiPost('/api/discounts', payload);
    showToast('Акция сохранена', 'gold');
    document.getElementById('discountFormWrap').style.display = 'none';
    loadDiscountsAdmin();
  } catch(e) { showToast('Ошибка: ' + e.message, 'err'); }
}

async function toggleDiscountVisibility(id, visible) {
  const d = allDiscountsAdmin.find(x => x.id === id);
  if(!d) return;
  try {
    await apiPut('/api/discounts/' + id, {...d, visible});
    showToast(visible ? 'Акция показана' : 'Акция скрыта', 'gold');
    loadDiscountsAdmin();
  } catch(e) { showToast('Ошибка', 'err'); }
}

async function deleteDiscount(id) {
  if(!confirm('Удалить эту акцию?')) return;
  try {
    await fetch(`${API_BASE}/api/discounts/${id}`, {
      method: 'DELETE',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    showToast('Акция удалена', 'err');
    loadDiscountsAdmin();
  } catch(e) { showToast('Ошибка удаления', 'err'); }
}

// ============================================================
// ФОТО И МЕДИА: фото акций и мест (загрузка в одном месте)
// ============================================================
let mediaPending = null;

function mediaEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function loadMediaItems() {
  try {
    const [discounts, places] = await Promise.all([apiGet('/api/discounts/all'), apiGet('/api/places/all')]);
    allDiscountsAdmin = discounts || [];
    allPlacesAdmin = places || [];
  } catch(e) {
    const err = '<div style="color:var(--text-muted);padding:12px">Ошибка загрузки</div>';
    document.getElementById('mediaDiscountsList').innerHTML = err;
    document.getElementById('mediaPlacesList').innerHTML = err;
    return;
  }
  renderMediaItems();
}

function mediaSlot(kind, id, field, file, caption, w, h, removable) {
  const thumb = file
    ? `<img src="${API_BASE}/data/photos/${mediaEsc(file)}" style="width:100%;height:100%;object-fit:cover;display:block">`
    : `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:20px;color:var(--text-muted)">🖼</div>`;
  return `
    <div style="display:flex;gap:10px;align-items:center">
      <div style="width:${w}px;height:${h}px;background:var(--black);border:1px solid var(--black-border);overflow:hidden;flex-shrink:0">${thumb}</div>
      <div>
        <div style="font-size:10px;color:var(--text-muted);margin-bottom:6px">${caption}</div>
        <button type="button" class="btn btn-ghost btn-sm" onclick="mediaPick('${kind}','${mediaEsc(id)}','${field}')">${file ? 'Заменить' : 'Загрузить'}</button>
        ${removable && file ? `<button type="button" class="btn btn-danger btn-sm" style="margin-left:6px" onclick="mediaRemove('${kind}','${mediaEsc(id)}','${field}')">Убрать</button>` : ''}
      </div>
    </div>`;
}

function mediaRow(title, hidden, slots) {
  return `
    <div style="padding:14px 16px;border:1px solid var(--black-border);background:var(--black-card);margin-bottom:8px">
      <div style="font-size:13px;color:var(--text-primary);margin-bottom:12px">${mediaEsc(title)}
        ${hidden ? '<span style="font-size:10px;color:var(--text-muted);background:rgba(90,74,48,.3);padding:2px 8px;margin-left:8px">скрыто</span>' : ''}
      </div>
      <div style="display:flex;gap:20px 28px;flex-wrap:wrap">${slots}</div>
    </div>`;
}

function renderMediaItems() {
  const dBox = document.getElementById('mediaDiscountsList');
  const pBox = document.getElementById('mediaPlacesList');
  if(!dBox || !pBox) return;
  dBox.innerHTML = allDiscountsAdmin.length
    ? allDiscountsAdmin.map(d => mediaRow(d.name || 'Без названия', d.visible === false,
        mediaSlot('discount', d.id, 'photo', d.photo, 'Компьютер (16:9)', 128, 72, false) +
        mediaSlot('discount', d.id, 'photo_mobile', d.photo_mobile, 'Телефон (9:16), необязательно', 56, 100, true)
      )).join('')
    : '<div style="color:var(--text-muted);padding:12px 0">Акций пока нет. Создайте акцию в разделе «Скидки и акции».</div>';
  pBox.innerHTML = allPlacesAdmin.length
    ? allPlacesAdmin.map(p => mediaRow(p.name || 'Без названия', p.visible === false,
        mediaSlot('place', p.id, 'photo', p.photo, 'Фото места (3:2)', 120, 80, true)
      )).join('')
    : '<div style="color:var(--text-muted);padding:12px 0">Мест пока нет. Добавьте место в разделе «Куда сходить».</div>';
}

const MEDIA_KINDS = {
  discount: { purpose: 'discount', path: '/api/discounts/', list: () => allDiscountsAdmin, okMsg: 'Фото акции сохранено' },
  place:    { purpose: 'place',    path: '/api/places/',    list: () => allPlacesAdmin,    okMsg: 'Фото места сохранено' },
};

function mediaPick(kind, id, field) {
  mediaPending = {kind, id, field};
  const f = document.getElementById('mediaItemFile');
  f.value = '';
  f.click();
}

async function mediaSaveField(kind, id, field, filename) {
  const cfg = MEDIA_KINDS[kind];
  const item = cfg.list().find(x => String(x.id) === String(id));
  if(!item) throw new Error('Элемент не найден, обновите страницу');
  await apiPut(cfg.path + id, {...item, [field]: filename});
}

async function mediaItemFileChosen() {
  const f = document.getElementById('mediaItemFile');
  const file = f.files[0];
  const pend = mediaPending;
  if(!file || !pend) return;
  if(file.size > 10 * 1024 * 1024) { showToast('Файл слишком большой (макс. 10 МБ)', 'err'); return; }
  const cfg = MEDIA_KINDS[pend.kind];
  const item = cfg.list().find(x => String(x.id) === String(pend.id));
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', (item && item.name) || (pend.kind === 'discount' ? 'Акция' : 'Место'));
  formData.append('purpose', cfg.purpose);
  try {
    showToast('Загружаю фото...', 'gold');
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    if(!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    await mediaSaveField(pend.kind, pend.id, pend.field, data.filename);
    showToast(cfg.okMsg, 'gold');
    await loadMediaItems();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  } finally {
    f.value = '';
    mediaPending = null;
  }
}

async function mediaRemove(kind, id, field) {
  if(!confirm('Убрать это фото?')) return;
  try {
    await mediaSaveField(kind, id, field, '');
    showToast('Фото убрано', 'gold');
    await loadMediaItems();
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// ВКЛАДКИ В «НАСТРОЙКАХ САЙТА»
let currentSiteTab = 'brand';
function showSiteTab(name) {
  currentSiteTab = name;
  document.querySelectorAll('#ssTabs .ss-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('#panel-sitesettings [data-ss-tab]').forEach(el => {
    el.style.display = el.dataset.ssTab.split(' ').includes(name) ? '' : 'none';
  });
}

// ДАННЫЕ АРЕНДОДАТЕЛЯ (Настройки → Система)
async function loadLandlord() {
  try {
    const d = await apiGet('/api/landlord');
    document.getElementById('landlordBrand').value = d.brand_name || '';
    document.getElementById('landlordDomain').value = d.domain || '';
    document.getElementById('landlordAddress').value = d.address || '';
  } catch(e) {}
}

async function saveLandlord() {
  try {
    const d = await apiPost('/api/landlord', {
      brand_name: document.getElementById('landlordBrand').value.trim(),
      domain:     document.getElementById('landlordDomain').value.trim(),
      address:    document.getElementById('landlordAddress').value.trim()
    });
    document.getElementById('landlordBrand').value = d.brand_name || '';
    document.getElementById('landlordDomain').value = d.domain || '';
    document.getElementById('landlordAddress').value = d.address || '';
    showToast('Данные арендодателя сохранены', 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

// REVIEWS ADMIN
let allReviewsAdmin = [];

async function loadReviewsAdmin() {
  try {
    allReviewsAdmin = await apiGet('/api/reviews/all');
    renderReviewsAdmin(allReviewsAdmin);
  } catch(e) {
    document.getElementById('reviewsList').innerHTML = '<div style="color:var(--text-muted);padding:20px">Ошибка загрузки отзывов</div>';
  }
}

function renderReviewsAdmin(reviews) {
  const list = document.getElementById('reviewsList');
  if (!reviews || reviews.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Отзывов пока нет — нажмите «+ Добавить отзыв»</div>';
    return;
  }
  const stars = n => '★'.repeat(n)+'☆'.repeat(5-n);
  list.innerHTML = reviews.map(r => `
    <div style="background:var(--black-card);border:1px solid ${r.visible ? 'var(--black-border)' : 'rgba(90,74,48,.4)'};padding:16px 20px;margin-bottom:12px;display:flex;gap:16px;align-items:flex-start">
      <div style="flex:1">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
          <span style="color:var(--gold);font-size:12px">${stars(r.rating||5)}</span>
          <span style="font-size:12px;color:var(--text-primary)">${r.author}</span>
          ${r.date ? `<span style="font-size:10px;color:var(--text-muted)">${r.date}</span>` : ''}
          ${!r.visible ? '<span style="font-size:10px;color:var(--text-muted);background:rgba(90,74,48,.3);padding:2px 8px">скрыт</span>' : ''}
        </div>
        <div style="font-size:12px;color:var(--text-secondary);line-height:1.6">${r.text.replace(/\n/g,'<br>')}</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">
        <button class="btn btn-ghost btn-sm" onclick="editReview('${r.id}')">✎</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleReviewVisibility('${r.id}', ${!r.visible})">${r.visible ? '👁' : '👁‍🗨'}</button>
        <button class="btn btn-danger btn-sm" onclick="deleteReview('${r.id}')">✕</button>
      </div>
    </div>
  `).join('');
}

function showAddReviewForm() {
  document.getElementById('reviewEditId').value = '';
  document.getElementById('reviewAuthor').value = '';
  document.getElementById('reviewText').value = '';
  document.getElementById('reviewRating').value = 5;
  document.getElementById('reviewDate').value = '';
  document.getElementById('reviewFormTitle').textContent = 'Новый отзыв';
  document.getElementById('reviewForm').style.display = 'block';
}

function editReview(id) {
  const r = allReviewsAdmin.find(x => x.id === id);
  if (!r) return;
  document.getElementById('reviewEditId').value = r.id;
  document.getElementById('reviewAuthor').value = r.author;
  document.getElementById('reviewText').value = r.text;
  document.getElementById('reviewRating').value = r.rating || 5;
  document.getElementById('reviewDate').value = r.date || '';
  document.getElementById('reviewFormTitle').textContent = 'Редактировать отзыв';
  document.getElementById('reviewForm').style.display = 'block';
}

function cancelReviewForm() {
  document.getElementById('reviewForm').style.display = 'none';
}

async function saveReview() {
  const id      = document.getElementById('reviewEditId').value;
  const author  = document.getElementById('reviewAuthor').value.trim();
  const text    = document.getElementById('reviewText').value.trim();
  const rating  = parseInt(document.getElementById('reviewRating').value) || 5;
  const date    = document.getElementById('reviewDate').value.trim();
  if (!author || !text) { showToast('Заполните имя и текст отзыва', 'err'); return; }
  const payload = { author, text, rating, date, visible: true };
  try {
    if (id) {
      await apiPut('/api/reviews/' + id, payload);
    } else {
      await apiPost('/api/reviews', payload);
    }
    document.getElementById('reviewForm').style.display = 'none';
    showToast('Отзыв сохранён', 'gold');
    loadReviewsAdmin();
  } catch(e) {
    showToast('Ошибка сохранения: ' + e.message, 'err');
  }
}

async function toggleReviewVisibility(id, visible) {
  const r = allReviewsAdmin.find(x => x.id === id);
  if (!r) return;
  try {
    await apiPut('/api/reviews/' + id, {...r, visible});
    showToast(visible ? 'Отзыв показан' : 'Отзыв скрыт', 'gold');
    loadReviewsAdmin();
  } catch(e) {
    showToast('Ошибка', 'err');
  }
}

async function deleteReview(id) {
  if (!confirm('Удалить отзыв?')) return;
  try {
    await fetch(`${API_BASE}/api/reviews/${id}`, {
      method: 'DELETE',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    showToast('Отзыв удалён', 'err');
    loadReviewsAdmin();
  } catch(e) {
    showToast('Ошибка удаления', 'err');
  }
}
// HOUSE RULES
async function loadHouseRules() {
  try {
    const r = await fetch(`${API_BASE}/api/house-rules`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    document.getElementById('houseRulesEditor').value = await r.text();
  } catch(e) { document.getElementById('houseRulesEditor').value = 'Ошибка загрузки'; }
}
async function saveHouseRules() {
  try {
    await apiPost('/api/house-rules', {text: document.getElementById('houseRulesEditor').value});
    showToast('Правила проживания сохранены', 'gold');
  } catch(e) { showToast('Ошибка сохранения', 'err'); }
}

