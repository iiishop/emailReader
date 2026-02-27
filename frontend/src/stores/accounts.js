import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref([])
  const loading = ref(false)
  const error = ref(null)

  /** 当前选中的账号 account_id */
  const selectedAccountId = ref(null)

  const selectedAccount = computed(() =>
    accounts.value.find(a => a.account_id === selectedAccountId.value) ?? null
  )

  async function fetchAccounts() {
    loading.value = true
    error.value = null
    try {
      const res = await fetch('/api/accounts')
      const data = await res.json()
      if (data.success) {
        accounts.value = data.accounts
        // 默认选中 default 账号
        if (!selectedAccountId.value) {
          const def = data.accounts.find(a => a.is_default) ?? data.accounts[0]
          if (def) selectedAccountId.value = def.account_id
        }
      } else {
        error.value = data.error
      }
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  function selectAccount(accountId) {
    selectedAccountId.value = accountId
  }

  return { accounts, loading, error, selectedAccountId, selectedAccount, fetchAccounts, selectAccount }
})
