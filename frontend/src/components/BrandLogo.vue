<template>
  <span class="resume-branch-logo" aria-label="ResumeBranch">
    <img src="/icon.svg?v=5" alt="" />
    <span>ResumeBranch</span>
  </span>
</template>

<style scoped>
.resume-branch-logo {
  display: inline-flex;
  align-items: center;
  gap: 0.62rem;
  color: #f4f4f6;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 1.25rem;
  line-height: 1;
  letter-spacing: -0.035em;
  white-space: nowrap;
}

.resume-branch-logo img {
  width: 22px;
  height: 22px;
  opacity: 1;
}

@media (max-width: 640px) {
  .resume-branch-logo {
    gap: 0.5rem;
    font-size: 1.08rem;
  }

  .resume-branch-logo img {
    width: 19px;
    height: 19px;
  }
}
</style>
