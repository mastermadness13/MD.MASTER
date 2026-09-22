/**
 * bottom_nav.js — mobile app bottom navigation (see bottom_nav.html).
 *
 *  - FAB / "more" button open the bottom sheet dialog, one section at a time.
 *  - Backdrop tap, Escape, or picking a row closes it; body scroll locks.
 *  - The bar hides while scrolling down and reappears on scroll up
 *    (TikTok-style breathing room) once the user is past the top.
 *
 * Desktop (>=1024px) never renders the bar, so nothing happens there.
 */
(function () {
  'use strict';

  var nav = document.getElementById('bottomNav');
  if (!nav || document.body.hasAttribute('data-skip-mobile-js')) return;

  var dialog = document.getElementById('bnSheetDialog');
  if (!dialog) return;

  var sectionCache = {};
  function section(name) {
    if (!sectionCache[name]) {
      sectionCache[name] = dialog.querySelector('[data-bn-section="' + name + '"]');
    }
    return sectionCache[name];
  }

  function openSheet(name) {
    ['quick', 'more'].forEach(function (n) {
      var s = section(n);
      if (s) s.hidden = n !== (name || 'quick');
    });
    dialog.hidden = false;
    requestAnimationFrame(function () {
      dialog.classList.add('show');
      document.body.classList.add('sheet-open');
    });
  }

  function closeSheet() {
    if (!dialog.classList.contains('show')) return;
    dialog.classList.remove('show');
    document.body.classList.remove('sheet-open');
    setTimeout(function () { dialog.hidden = true; }, 260);
  }

  window.toggleBnSheet = function (name) {
    if (dialog.classList.contains('show')) closeSheet();
    else openSheet(name || 'quick');
  };
  window.closeBnSheet = closeSheet;

  dialog.addEventListener('click', function (e) {
    if (e.target.closest('[data-bn-close]')) { closeSheet(); return; }
    /* tap on the obscured backdrop (not the sheet) */
    if (!e.target.closest('.bn-sheet')) closeSheet();
  });
  /* picking any row navigates/acts — dismiss the sheet right after */
  dialog.addEventListener('click', function (e) {
    if (e.target.closest('.bn-item-row')) setTimeout(closeSheet, 120);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeSheet();
  });

  /* Hide on scroll down, reveal on scroll up */
  var lastY = window.pageYOffset || 0;
  window.addEventListener('scroll', function () {
    var y = window.pageYOffset || 0;
    if (Math.abs(y - lastY) < 14) return;
    document.body.classList.toggle('bn-hidden', y > lastY && y > 140);
    lastY = y;
  }, { passive: true });
})();


(function(){
  var MAX = 12;
  var tbody = document.getElementById('ccTheoreticalCurriculumBody');
  var total = document.getElementById('ccTheoreticalWeeksTotal');
  var addBtn = document.getElementById('ccAddTheoreticalRow');
  if(!tbody) return;

  // 1) تمدد تلقائي لكل textarea (لا شريط تمرير)
  function grow(t){
    t.style.overflow='hidden';
    t.style.height='auto';
    t.style.height=(t.scrollHeight+2)+'px';
  }
  function bind(t){
    if(t._g) return; t._g=1;
    t.addEventListener('input',function(){grow(t)});
    grow(t);
  }
  document.querySelectorAll('textarea').forEach(bind);

  // 2) حساب الأسابيع
  function calcWeeks(){
    var s=0;
    tbody.querySelectorAll('input[name="theoretical_curriculum_weeks[]"]').forEach(function(i){
      var v=parseInt(i.value,10); if(v>0) s+=v;
    });
    if(total) total.textContent=s;
    if(addBtn) addBtn.disabled = s>=MAX;
    return s;
  }

  // 3) صف جديد بنفس بنية صفك الحالي
  function newRow(){
    var tr=document.createElement('tr');
    tr.innerHTML =
      '<td class="align-middle text-center font-bold text-black row-index"></td>' +
      '<td class="align-middle"><textarea name="theoretical_curriculum_topic[]" rows="2" placeholder="الموضوع"></textarea></td>' +
      '<td class="align-middle"><input type="number" name="theoretical_curriculum_weeks[]" min="1" value="1" class="text-center font-semibold week-input"></td>' +
      '<td class="align-middle"><textarea name="theoretical_curriculum_topic_en[]" rows="2" dir="ltr" placeholder="Topic (EN)" class="font-[\'Inter\'] text-sm"></textarea></td>' +
      '<td class="align-middle text-center no-print"><button type="button" class="cc-curriculum-remove text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 p-1 rounded font-bold cursor-pointer text-xs">✕</button></td>';
    tbody.appendChild(tr);
    tr.querySelectorAll('textarea').forEach(bind);
    return tr;
  }

  function renumber(){
    tbody.querySelectorAll('tr').forEach(function(tr,i){
      var c=tr.querySelector('.row-index'); if(c) c.textContent=i+1;
    });
  }

  function tryAdd(){
    if(calcWeeks()>=MAX) return;
    newRow(); renumber(); calcWeeks();
  }

  // 4) عند الكتابة في الصف الأخير → صف جديد
  tbody.addEventListener('input',function(e){
    if(e.target.tagName==='TEXTAREA') grow(e.target);
    var tr=e.target.closest('tr');
    if(!tr||e.target.tagName!=='TEXTAREA') return;
    var rows=tbody.querySelectorAll('tr');
    if(rows[rows.length-1]!==tr) return;
    if(!e.target.value.trim()) return;
    tryAdd();
  });

  // 5) عند تغيير رقم الأسبوع → احترام سقف 12
  tbody.addEventListener('change',function(e){
    if(e.target.name!=='theoretical_curriculum_weeks[]') return;
    var v=parseInt(e.target.value,10); if(!v||v<1) v=1;
    var other=0;
    tbody.querySelectorAll('input[name="theoretical_curriculum_weeks[]"]').forEach(function(i){
      if(i!==e.target){var x=parseInt(i.value,10); if(x>0) other+=x;}
    });
    if(other+v>MAX) v=Math.max(1,MAX-other);
    e.target.value=v;
    calcWeeks();
  });

  // 6) زر الحذف (موجود مسبقاً في صفوفك)
  tbody.addEventListener('click',function(e){
    var b=e.target.closest('.cc-curriculum-remove');
    if(!b) return;
    var tr=b.closest('tr');
    if(tbody.querySelectorAll('tr').length<=1){
      tr.querySelectorAll('textarea').forEach(function(t){t.value='';grow(t)});
      var w=tr.querySelector('input[name="theoretical_curriculum_weeks[]"]'); if(w)w.value=1;
    } else { tr.remove(); }
    renumber(); calcWeeks();
  });

  // 7) زر «صف جديد»
  if(addBtn) addBtn.addEventListener('click',function(e){
    e.preventDefault();
    if(calcWeeks()>=MAX){ alert('تم الوصول للحد الأقصى: 12 أسبوعاً'); return; }
    tryAdd();
  });

  // 8) زر «إعادة تعيين» يُضاف تلقائياً بجانب «صف جديد»
  if(addBtn && addBtn.parentNode){
    var reset=document.createElement('button');
    reset.type='button'; reset.textContent='↺ إعادة تعيين';
    reset.className='flex items-center gap-1.5 bg-white hover:bg-red-50 text-red-700 px-3 py-1.5 rounded-md text-xs font-bold transition border border-red-200 cursor-pointer shadow-sm';
    reset.style.marginInlineStart='8px';
    reset.onclick=function(){
      if(!confirm('إعادة تعيين الجدول النظري؟')) return;
      tbody.innerHTML='';
      var tr=newRow();
      tr.querySelector('input[name="theoretical_curriculum_weeks[]"]').value=1;
      renumber(); calcWeeks();
    };
    addBtn.parentNode.appendChild(reset);
  }

  // 9) زر «تصدير CSV» يُضاف تلقائياً
  if(addBtn && addBtn.parentNode){
    var csv=document.createElement('button');
    csv.type='button'; csv.textContent='⬇ تصدير CSV';
    csv.className='flex items-center gap-1.5 bg-white hover:bg-blue-50 text-blue-700 px-3 py-1.5 rounded-md text-xs font-bold transition border border-blue-200 cursor-pointer shadow-sm';
    csv.style.marginInlineStart='8px';
    csv.onclick=function(){
      function esc(s){s=(s||'').replace(/\r?\n/g,' ');return /[",]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;}
      var lines=[['#','الموضوع','الأسابيع','Topic (EN)'].join(',')];
      tbody.querySelectorAll('tr').forEach(function(tr,i){
        var a=tr.querySelector('textarea[name="theoretical_curriculum_topic[]"]');
        var w=tr.querySelector('input[name="theoretical_curriculum_weeks[]"]');
        var b=tr.querySelector('textarea[name="theoretical_curriculum_topic_en[]"]');
        lines.push([i+1, a?a.value:'', w?w.value:'', b?b.value:''].map(esc).join(','));
      });
      var blob=new Blob(['\uFEFF'+lines.join('\r\n')],{type:'text/csv;charset=utf-8;'});
      var a=document.createElement('a');
      a.href=URL.createObjectURL(blob); a.download='theoretical.csv';
      document.body.appendChild(a); a.click();
      setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},100);
    };
    addBtn.parentNode.appendChild(csv);
  }

  // تشغيل مبدئي
  renumber(); calcWeeks();
})();


(function(){
  var th  = document.getElementById('theoryHours');
  var ph  = document.getElementById('practicalHours');
  var tuh = document.querySelector('input[name="tutorial_hours"]');
  var tot = document.querySelector('input[data-mirror="total_hours"]');
  var hid = document.querySelector('input[name="total_hours"]');
  if(!th || !ph || !tot) return;

  function num(el){ var v = parseInt(el && el.value, 10); return isNaN(v) ? 0 : v; }

  function recalc(){
    var total = num(th) + num(ph) + num(tuh);
    tot.value = total;
    if(hid) hid.value = total;
  }

  [th, ph, tuh].forEach(function(el){
    if(!el) return;
    el.addEventListener('input',  recalc);
    el.addEventListener('change', recalc);
  });

  recalc();
})();
