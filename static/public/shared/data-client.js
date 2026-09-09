/**
 * Data Client - Loads and caches data from static JSON files
 * Provides filtering and querying capabilities for all data types
 */
(function () {
class DataClient {
  constructor() {
    this.cache = new Map();
    const root = (window.Utils && window.Utils.publicRoot) ? Utils.publicRoot(document.currentScript) : '';
    this.basePath = root + 'data/';
  }

  /**
   * Load a JSON file with caching
   */
  async load(file) {
    if (this.cache.has(file)) return this.cache.get(file);
    let data;
    try {
      const response = await fetch(`${this.basePath}${file}`);
      if (!response.ok) throw new Error(`Failed to load ${file}: ${response.status}`);
      data = await response.json();
    } catch (err) {
      const key = file.replace(/\.json$/, '');
      if (window.INLINE_DATA && window.INLINE_DATA[key]) {
        data = window.INLINE_DATA[key];
      } else {
        throw err;
      }
    }
    this.cache.set(file, data);
    return data;
  }

  /**
   * Get all non-hidden departments
   */
  async getDepartments() {
    const data = await this.load('departments.json');
    return data.departments.filter(d => !d.hidden);
  }

  /**
   * Get all departments (including hidden)
   */
  async getAllDepartments() {
    const data = await this.load('departments.json');
    return data.departments;
  }

  /**
   * Get a single department by ID
   */
  async getDepartment(id) {
    const data = await this.load('departments.json');
    return data.departments.find(d => d.id === id);
  }

  /**
   * Get courses with optional filters
   * @param {Object} filters - { departmentId, semester, year, search }
   */
  async getCourses(filters = {}) {
    const data = await this.load('courses.json');
    let courses = data.courses;
    if (filters.departmentId) courses = courses.filter(c => c.departmentId === filters.departmentId);
    if (filters.semester) courses = courses.filter(c => c.semester === filters.semester);
    if (filters.year) courses = courses.filter(c => c.year === filters.year);
    if (filters.search) {
      const q = filters.search.toLowerCase();
      courses = courses.filter(c => 
        c.name.toLowerCase().includes(q) || 
        c.code.toLowerCase().includes(q) ||
        c.department.toLowerCase().includes(q)
      );
    }
    return courses;
  }

  /**
   * Get a single course by ID
   */
  async getCourse(id) {
    const data = await this.load('courses.json');
    return data.courses.find(c => c.id === id);
  }

  /**
   * Get timetable entries with optional filters
   * @param {Object} filters - { departmentId, semester }
   */
  async getTimetable(filters = {}) {
    const data = await this.load('timetable.json');
    let entries = data.entries;
    if (filters.departmentId) entries = entries.filter(e => e.departmentId === filters.departmentId);
    if (filters.semester) entries = entries.filter(e => e.semester === filters.semester);
    return entries;
  }

  /**
   * Get exams with optional filters
   * @param {Object} filters - { departmentId, semester }
   */
  async getExams(filters = {}) {
    const data = await this.load('exams.json');
    let exams = data.exams;
    if (filters.departmentId) exams = exams.filter(e => e.departmentId === filters.departmentId);
    if (filters.semester) exams = exams.filter(e => e.semester === filters.semester);
    return exams;
  }

  /**
   * Get rooms with optional department filter
   */
  async getRooms(departmentId) {
    const data = await this.load('rooms.json');
    if (departmentId) return data.rooms.filter(r => r.departmentId === departmentId);
    return data.rooms;
  }

  /**
   * Get teachers with optional department filter
   */
  async getTeachers(departmentId) {
    const data = await this.load('teachers.json');
    if (departmentId) return data.teachers.filter(t => t.departmentId === departmentId);
    return data.teachers;
  }

  /**
   * Get time periods
   */
  async getPeriods() {
    const data = await this.load('periods.json');
    return data.periods.filter(p => p.enabled);
  }

  /**
   * Get all periods (including disabled)
   */
  async getAllPeriods() {
    const data = await this.load('periods.json');
    return data.periods;
  }

  /**
   * Get lookup tables
   */
  async getLookups() {
    return this.load('lookups.json');
  }

  /**
   * Clear cache (useful for development)
   */
  clearCache() {
    this.cache.clear();
  }
}

// Export singleton instance
window.DataClient = new DataClient();

// Also export class for testing
window.DataClientClass = DataClient;
})();