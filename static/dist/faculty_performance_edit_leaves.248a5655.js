function addLeaveRow(){const r=document.getElementById("leaves-container"),o=(window.FACULTY_EDIT_LEAVES_BOOT||{}).leaveTypes||[];let e='<option value="">\u2014 \u0627\u062E\u062A\u0631 \u2014</option>';o.forEach(t=>{e+='<option value="'+t+'">'+t+"</option>"});const n=`
    <div class="leave-row flex flex-wrap items-end gap-2 p-3 rounded-xl border border-outline-variant bg-surface-dim">
      <div class="flex-1 min-w-[160px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0646\u0648\u0639 \u0627\u0644\u0642\u0631\u0627\u0631</label>
        <select name="leave_type[]" required class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">${e}</select>
      </div>
      <div class="flex-1 min-w-[130px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0631\u0642\u0645 \u0627\u0644\u0642\u0631\u0627\u0631</label>
        <input type="text" name="decision_number[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="flex-1 min-w-[130px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u062C\u0647\u0629 \u0627\u0644\u0625\u0635\u062F\u0627\u0631</label>
        <input type="text" name="decision_authority[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u062A\u0627\u0631\u064A\u062E \u0627\u0644\u0642\u0631\u0627\u0631</label>
        <input type="date" name="decision_date[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0645\u0646 \u062A\u0627\u0631\u064A\u062E</label>
        <input type="date" name="start_date[]" required class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-32">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0625\u0644\u0649 \u062A\u0627\u0631\u064A\u062E</label>
        <input type="date" name="end_date[]" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="w-28">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0627\u0644\u0633\u0627\u0639\u0627\u062A</label>
        <input type="number" name="hours[]" value="0" min="1" max="24" step="1" inputmode="numeric" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none">
      </div>
      <div class="flex-1 min-w-[100px]">
        <label class="block text-xs font-bold text-on-surface-variant mb-1">\u0645\u0644\u0627\u062D\u0638\u0627\u062A</label>
        <input type="text" name="notes[]" value="" class="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary outline-none" placeholder="\u0627\u062E\u062A\u064A\u0627\u0631\u064A">
      </div>
      <button type="button" onclick="this.closest('.leave-row').remove()" class="p-2 rounded-lg hover:bg-red-50 text-red-500 transition">
        <span class="material-symbols-outlined text-lg">delete</span>
      </button>
    </div>`;r.insertAdjacentHTML("beforeend",n)}
