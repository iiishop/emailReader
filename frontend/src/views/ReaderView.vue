<template>
  <div class="reader-layout">
    <SideBar />
    <EmailList />
    <EmailViewer />
  </div>
</template>

<script setup>
import SideBar     from '../components/SideBar.vue'
import EmailList   from '../components/EmailList.vue'
import EmailViewer from '../components/EmailViewer.vue'
</script>

<style scoped>
.reader-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}
</style>
