<template>
  <span class="resume-branch-logo" aria-label="ResumeBranch">
    <img src="/icon.svg" alt="" />
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
  font-size: 1.42rem;
  line-height: 1;
  letter-spacing: -0.035em;
  white-space: nowrap;
}

.resume-branch-logo img {
  width: 24px;
  height: 24px;
  filter: grayscale(1) brightness(0) invert(1);
  opacity: 0.94;
}

@media (max-width: 640px) {
  .resume-branch-logo {
    gap: 0.5rem;
    font-size: 1.2rem;
  }

  .resume-branch-logo img {
    width: 21px;
    height: 21px;
  }
}
</style>
