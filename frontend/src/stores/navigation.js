import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useNavigationStore = defineStore('navigation', () => {
  /** 当前页面：'dashboard' | 'reader' */
  const currentPage = ref('dashboard')

  function navigate(page) {
    currentPage.value = page
  }

  return { currentPage, navigate }
})
