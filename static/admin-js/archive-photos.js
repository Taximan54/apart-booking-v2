// admin-js/archive-photos.js: Архив договоров, галерея, ручная бронь.
// Часть админки (ранее единого admin.js). Файлы подключаются подряд, в порядке из admin.html.
// CONTRACTS ARCHIVE
const PASSPORT_SLOT_LABELS = {main: '📄 Паспорт (главная)', reg1: '🏠 Паспорт (прописка)'};

async function loadContractsArchive() {
  const container = document.getElementById('contractsArchiveContent');
  container.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Загрузка...</div>';
  try {
    const contracts = await apiGet('/api/contracts');
    if (!contracts || contracts.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Договоров пока нет</div>';
      return;
    }
    container.innerHTML = `
      <table class="tbl">
        <thead><tr>
          <th>Бронь</th><th>Гость</th><th>Даты</th><th>Сумма</th><th>Создан</th><th>Документы</th><th></th>
        </tr></thead>
        <tbody>
          ${contracts.map(c => `
            <tr>
              <td data-label="Бронь" style="color:var(--gold);font-size:12px">${c.ref}</td>
              <td data-label="Гость">
                <div style="font-size:12px;color:var(--text-primary)">${c.guest_name || '—'}</div>
                <div style="font-size:11px;color:var(--text-muted)">${c.guest_email || ''}</div>
              </td>
              <td data-label="Даты" style="font-size:12px">${c.check_in || '—'} → ${c.check_out || '—'}</td>
              <td data-label="Сумма" style="font-size:12px">${c.total_price ? '₽' + Number(c.total_price).toLocaleString('ru') : '—'}</td>
              <td data-label="Создан" style="font-size:11px;color:var(--text-muted)">${c.created}</td>
              <td data-label="Документы" style="display:flex;flex-wrap:wrap;gap:6px">
                ${c.has_contract_pdf ? `<button class="btn btn-outline btn-sm" onclick="downloadArchivePdf('${c.ref}','contract')">📄 Договор (PDF)</button>` : ''}
                ${c.has_consent_pdf ? `<button class="btn btn-outline btn-sm" onclick="downloadArchivePdf('${c.ref}','consent')">📄 Согласие (PDF)</button>` : ''}
                ${!c.has_contract_pdf && c.has_draft ? `<button class="btn btn-ghost btn-sm" onclick="downloadContract('${c.ref}', '${(c.guest_name || c.ref).replace(/'/g,"\\'")}')">Черновик (.txt)</button>` : ''}
                ${(c.passport_photo_slots||[]).map(slot => `<button class="btn btn-ghost btn-sm" onclick="viewArchivePassportPhoto('${c.passport_ref}','${slot}')">${PASSPORT_SLOT_LABELS[slot]}</button>`).join('')}
                ${!c.has_contract_pdf && !c.has_draft && !c.has_passport_photo ? '—' : ''}
              </td>
              <td data-label=""><button class="btn btn-ghost btn-icon" title="Удалить из архива" onclick="deleteArchiveContract('${c.ref}','${(c.guest_name || c.ref).replace(/'/g,"\\'")}')">🗑</button></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch(e) {
    container.innerHTML = '<div style="color:var(--text-muted);padding:20px">Ошибка загрузки: ' + e.message + '</div>';
  }
}

async function downloadArchivePdf(ref, docType) {
  try {
    const resp = await fetch(`${API_BASE}/api/admin/contract-pdf/${ref}/${docType}`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if (!resp.ok) throw new Error('Документ не найден');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  } catch(e) {
    showToast('Не удалось открыть документ: ' + e.message, 'err');
  }
}

async function viewArchivePassportPhoto(ref, slot) {
  try {
    const resp = await fetch(`${API_BASE}/api/admin/passport-photo/${ref}/${slot}`, {
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if(!resp.ok) throw new Error('not found');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  } catch(e) {
    showToast('Фото не найдено', 'err');
  }
}

async function deleteArchiveContract(ref, guestName) {
  if (!confirm(`Удалить договор «${guestName}» (${ref}) из архива безвозвратно?\n\nБудут удалены черновик, подписанный PDF, согласие на ПД и фото паспорта. Если по этой брони есть запись в списке броней — она тоже будет удалена.`)) return;
  try {
    await apiDelete(`/api/contracts/${ref}`);
    showToast('Договор удалён из архива', 'gold');
    loadContractsArchive();
  } catch(e) {
    showToast('Ошибка удаления: ' + e.message, 'err');
  }
}

// PHOTOS ADMIN
let photosOrder = [];

async function loadPhotosAdmin() {
  try {
    const photos = await apiGet('/api/photos');
    photosOrder = photos.map(p => p.filename);
    renderPhotosAdmin(photos);
  } catch(e) {
    document.getElementById('photosGrid').innerHTML = '<div style="color:var(--text-muted)">Ошибка загрузки</div>';
  }
}

function renderPhotosAdmin(photos) {
  const grid = document.getElementById('photosGrid');
  if (!photos || photos.length === 0) {
    grid.innerHTML = '<div style="color:var(--text-muted);padding:20px;text-align:center">Фотографий пока нет — загрузите первое фото</div>';
    return;
  }
  grid.innerHTML = photos.map((p, i) => `
    <div class="photo-card" data-filename="${p.filename}" style="background:var(--black-card);border:1px solid var(--black-border);position:relative">
      <img src="${p.url}" style="width:100%;height:140px;object-fit:cover;display:block">
      <div style="padding:10px 12px">
        <input type="text" value="${p.label}" placeholder="Подпись к фото"
          style="width:100%;background:var(--black);border:1px solid var(--black-border);color:var(--text-secondary);padding:6px 8px;font-family:'Montserrat',sans-serif;font-size:11px;margin-bottom:8px;outline:none"
          onchange="updatePhotoLabel('${p.filename}', this.value)">
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" style="flex:1" onclick="movePhoto('${p.filename}', -1)">↑</button>
          <button class="btn btn-ghost btn-sm" style="flex:1" onclick="movePhoto('${p.filename}', 1)">↓</button>
          <button class="btn btn-danger btn-sm" onclick="deletePhoto('${p.filename}')">✕</button>
        </div>
      </div>
    </div>
  `).join('');
  document.getElementById('saveOrderBtn').style.display = 'block';
}

async function updatePhotoLabel(filename, label) {
  try {
    await apiPost(`/api/photos/${filename}/label`, {label});
    showToast('Подпись сохранена', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения подписи', 'err');
  }
}

async function uploadPhoto() {
  const file = document.getElementById('photoFile').files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) { showToast('Файл слишком большой (макс. 5 МБ)', 'err'); return; }
  const label = document.getElementById('photoLabel').value.trim();
  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', label);
  try {
    const resp = await fetch(`${API_BASE}/api/photos/upload`, {
      method: 'POST',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {},
      body: formData
    });
    if (!resp.ok) throw new Error(await resp.text());
    showToast('Фото загружено', 'gold');
    document.getElementById('photoFile').value = '';
    document.getElementById('photoLabel').value = '';
    loadPhotosAdmin();
  } catch(e) {
    showToast('Ошибка загрузки: ' + e.message, 'err');
  }
}

async function deletePhoto(filename, force) {
  if (!force && !confirm('Удалить это фото?')) return;
  try {
    const resp = await fetch(`${API_BASE}/api/photos/${filename}${force ? '?force=true' : ''}`, {
      method: 'DELETE',
      headers: ADMIN_TOKEN ? {'Authorization': 'Bearer ' + ADMIN_TOKEN} : {}
    });
    if (resp.status === 409) {
      const data = await resp.json().catch(() => ({}));
      const msg = (data.detail || 'Это фото сейчас где-то используется.') + '\n\nВсё равно удалить?';
      if (confirm(msg)) {
        return deletePhoto(filename, true);
      }
      return;
    }
    if (!resp.ok) {
      showToast('Ошибка удаления', 'err');
      return;
    }
    showToast('Фото удалено', 'err');
    loadPhotosAdmin();
  } catch(e) {
    showToast('Ошибка удаления', 'err');
  }
}

async function movePhoto(filename, dir) {
  const idx = photosOrder.indexOf(filename);
  if (idx === -1) return;
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= photosOrder.length) return;
  photosOrder.splice(idx, 1);
  photosOrder.splice(newIdx, 0, filename);
  await savePhotosOrder();
  loadPhotosAdmin();
}

async function savePhotosOrder() {
  try {
    await apiPost('/api/photos/reorder', {order: photosOrder});
    showToast('Порядок сохранён', 'gold');
  } catch(e) {
    showToast('Ошибка сохранения порядка', 'err');
  }
}

// MANUAL BOOKING (внешние площадки)
async function createManualBooking() {
  const payload = {
    source:       document.getElementById('mbSource').value,
    check_in:     document.getElementById('mbCheckIn').value,
    check_out:    document.getElementById('mbCheckOut').value,
    guest_name:   document.getElementById('mbGuestName').value.trim(),
    guest_phone:  document.getElementById('mbPhone').value.trim(),
    guest_email:  document.getElementById('mbEmail').value.trim(),
    guests_count: parseInt(document.getElementById('mbGuests').value) || 2,
    passport:     document.getElementById('mbPassport').value.trim(),
    total_price:  parseInt(document.getElementById('mbTotal').value) || 0,
    deposit:      parseInt(document.getElementById('mbDeposit').value) || 0,
    notes:        document.getElementById('mbNotes').value.trim(),
  };
  if(!payload.check_in || !payload.check_out) {
    showToast('Укажите даты заезда и выезда', 'err');
    return;
  }
  try {
    const res = await apiPost('/api/admin/manual-booking', payload);
    showToast(`Бронь ${res.booking_ref} создана`, 'gold');

    document.getElementById('mbLinkBox').style.display = 'block';
    document.getElementById('mbLinkInput').value = res.sign_link;
    document.getElementById('mbLinkNote').textContent = res.email_sent
      ? 'Ссылка также отправлена гостю на email.'
      : 'Email не указан — скопируй ссылку и отправь гостю вручную (например, в чат Авито).';

    ['mbGuestName','mbPhone','mbEmail','mbPassport','mbTotal','mbDeposit','mbNotes','mbCheckIn','mbCheckOut'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.getElementById('mbGuests').value = 2;
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

function copyMbLink() {
  const input = document.getElementById('mbLinkInput');
  input.select();
  navigator.clipboard?.writeText(input.value).then(() => {
    showToast('Ссылка скопирована', 'gold');
  }).catch(() => {
    document.execCommand('copy');
    showToast('Ссылка скопирована', 'gold');
  });
}

async function resendContractManual() {
  const ref = document.getElementById('resendBookingRef').value.trim();
  const email = document.getElementById('resendEmail').value.trim();
  if(!ref || !email) {
    showToast('Укажите номер брони и email', 'err');
    return;
  }
  try {
    await apiPost(`/api/admin/bookings/${ref}/resend-contract`, {email});
    showToast('Договор отправлен на ' + email, 'gold');
  } catch(e) {
    showToast('Ошибка: ' + e.message, 'err');
  }
}

