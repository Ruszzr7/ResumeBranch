<template>
  <div class="homepage" id="homepage">
    <!-- Hero Section -->
    <section class="hero">
      <div class="hero-bg"></div>
      <div class="hero-content">
        <h1 class="hero-title">
          <span class="hero-main-text">打造专业简历<br/>赢得理想 Offer</span>
        </h1>
        <p class="hero-desc">智能解析、一键优化、精准投递<br/>助你快速斩获心仪 Offer</p>
        <div class="hero-actions">
          <button class="btn-hero-primary" @click="handleCreateResume">
            立即创建简历
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        </div>
        <div class="hero-features">
          <div class="hero-feature-item">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
            <span>简历智能解析</span>
          </div>
          <div class="feature-divider"></div>
          <div class="hero-feature-item">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <span>边聊边改</span>
          </div>
          <div class="feature-divider"></div>
          <div class="hero-feature-item">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
              <line x1="16" y1="2" x2="16" y2="6"/>
              <line x1="8" y1="2" x2="8" y2="6"/>
              <line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
            <span>智能实时排版</span>
          </div>
          <div class="feature-divider"></div>
          <div class="hero-feature-item">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/>
              <line x1="3" y1="6" x2="21" y2="6"/>
              <path d="M16 10a4 4 0 0 1-8 0"/>
            </svg>
            <span>一键导出PDF</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Target Users Section -->
    <section class="users-section">
      <div class="section-inner">
        <h2 class="section-title">适用人群</h2>
        
        <!-- Tab Switcher -->
        <div class="target-tabs">
          <button 
            :class="['tab-btn', { active: activeTarget === 'intern' }]"
            @click="activeTarget = 'intern'"
          >
            寻找实习
          </button>
          <button 
            :class="['tab-btn', { active: activeTarget === 'campus' }]"
            @click="activeTarget = 'campus'"
          >
            校招应届
          </button>
          <button 
            :class="['tab-btn', { active: activeTarget === 'jobhop' }]"
            @click="activeTarget = 'jobhop'"
          >
            跳槽转型
          </button>
        </div>

        <!-- Tab Content -->
        <div class="target-content">
          <div v-if="activeTarget === 'intern'" class="target-card">
            <div class="target-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M22 10v6M2 10l10-5 10 5-10 5z"/>
                <path d="M6 12v5c3 3 9 3 12 0v-5"/>
              </svg>
            </div>
            <h3>正在寻找实习机会的学生</h3>
            <p>作为第一次踏入职场的学生，你可能还没有完整的简历经历，也不太了解 HR 最看重简历中的哪些部分。我们的 AI 简历助手可以帮你快速生成一份专业、突出优势的简历，让你在众多实习生候选人中脱颖而出，无论是名企大厂还是初创公司，都能给你带来更多面试机会。</p>
          </div>
          <div v-if="activeTarget === 'campus'" class="target-card">
            <div class="target-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M22 10v6M2 10l10-5 10 5-10 5z"/>
                <path d="M6 12v5c3 3 9 3 12 0v-5"/>
                <path d="M12 16v4"/>
              </svg>
            </div>
            <h3>准备参加校园招聘的应届毕业生</h3>
            <p>校招是应届生进入职场最重要的机会，但面对成千上万的求职者，如何让你的简历在 6 秒内抓住 HR 的眼球？通过与 AI 实时对话，帮你挖掘项目亮点、量化学习成果，优化简历内容，让你的简历在众多候选人中脱颖而出。</p>
          </div>
          <div v-if="activeTarget === 'jobhop'" class="target-card">
            <div class="target-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/>
                <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
              </svg>
            </div>
            <h3>计划跳槽的职场白领</h3>
            <p>工作几年后想要寻求更好的发展机会，却不知道如何更好地展示自己的工作成绩？我们的 AI 助手可以帮你梳理职业履历，挖掘过往工作中的亮点和成就，重新包装你的简历，让你在跳槽时能够成功转型或晋升到更高级别的岗位。</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Scenarios Section -->
    <section class="scenarios-section" style="background: white; border-bottom: 1px solid #e5e5e5;">
      <div class="section-inner">
        <h2 class="section-title">使用场景</h2>
        <div class="scenarios-grid">
          <div class="scenario-card">
            <div class="scenario-num">01</div>
            <h3>简历初创</h3>
            <p>没有简历？一键上传现有文档，AI 智能解析并生成结构化简历</p>
          </div>
          <div class="scenario-card">
            <div class="scenario-num">02</div>
            <h3>投递前优化</h3>
            <p>针对不同岗位要求，智能优化简历内容，提升匹配度和竞争力</p>
          </div>
          <div class="scenario-card">
            <div class="scenario-num">03</div>
            <h3>面试准备</h3>
            <p>基于简历内容，挖掘潜在面试问题，提前准备从容应对</p>
          </div>
          <div class="scenario-card">
            <div class="scenario-num">04</div>
            <h3>职业转型</h3>
            <p>梳理过往经验，挖掘可迁移能力，定制化简历助力转型</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Core Features Section -->
    <section class="scenarios-section" style="background: white; border-bottom: 1px solid #e5e5e5;">
      <div class="section-inner">
        <h2 class="section-title">核心功能</h2>
        <div class="scenarios-grid">
          <div class="scenario-card">
            <div class="scenario-num">01</div>
            <h3>简历智能解析</h3>
            <p>一键上传简历文档，AI自动识别生成结构化简历，支持PDF、图片格式</p>
          </div>
          <div class="scenario-card">
            <div class="scenario-num">02</div>
            <h3>边聊边改</h3>
            <p>通过对话与AI沟通，实时获取修改建议，AI智能优化简历</p>
          </div>
          <div class="scenario-card">
            <div class="scenario-num">03</div>
            <h3>智能实时排版</h3>
            <p>自动排版优化，实时预览效果，多种专业模板可选</p>
          </div>
          <div class="scenario-card">
            <div class="scenario-num">04</div>
            <h3>一键导出PDF</h3>
            <p>导出无水印专业版PDF，适配各招聘平台要求，提升投递效率</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="homepage-footer">
      <div class="section-inner">
        <div class="footer-brand">
          <span class="footer-logo">OfferFlow</span>
          <span class="footer-tagline">AI 智能简历助手</span>
        </div>
        <div class="footer-copy">© 2024 OfferFlow. All rights reserved.</div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ref } from 'vue'

const router = useRouter()
const activeTarget = ref('intern')

function handleCreateResume() {
  const token = localStorage.getItem('access_token')
  if (token) {
    router.push('/')
  } else {
    router.push('/register')
  }
}
</script>

<style scoped>
.homepage {
  min-height: 100vh;
  background-color: rgb(254, 253, 251);
  color: #303030;
  overflow: auto;
}

.section-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1.5rem;
}

/* Hero Section */
.hero {
  position: relative;
  min-height: 85vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6rem 1.5rem 4rem;
  overflow: hidden;
}

.hero-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: 
    radial-gradient(circle at 20% 80%, rgba(217, 119, 6, 0.08) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, rgba(48, 48, 48, 0.05) 0%, transparent 50%),
    url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='2.5' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)' opacity='0.03'/%3E%3C/svg%3E");
  background-blend-mode: normal, normal, overlay;
  z-index: 0;
}

.hero-content {
  position: relative;
  z-index: 1;
  text-align: center;
  max-width: 800px;
}

.hero-title {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-family: 'PingFang SC', 'Noto Sans SC', sans-serif;
  font-size: clamp(2.5rem, 8vw, 4.5rem);
  font-weight: 700;
  line-height: 1.15;
  color: #1a1a1a;
  margin: 0 0 1.5rem;
  letter-spacing: -0.02em;
}

.hero-title .product-name {
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: clamp(1.25rem, 4vw, 2rem);
  font-weight: 700;
  color: #d97706;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 0.5rem;
  text-shadow: 
    0 0 10px rgba(255, 255, 255, 0.8),
    0 0 20px rgba(255, 255, 255, 0.5),
    0 0 30px rgba(255, 255, 255, 0.3);
  animation: glow-pulse 2s ease-in-out infinite;
}

.hero-title .product-tagline {
  font-family: 'PingFang SC', 'Noto Sans SC', sans-serif;
  font-size: clamp(1rem, 2.5vw, 1.25rem);
  font-weight: 400;
  color: #666;
  margin-bottom: 1.5rem;
}

.hero-title .hero-main-text {
  display: block;
}

.hero-desc {
  font-size: 1.125rem;
  line-height: 1.8;
  color: #666;
  margin: 0 0 2.5rem;
}

.hero-actions {
  margin-bottom: 3rem;
}

.btn-hero-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 2rem;
  background: #303030;
  border: 1px solid #303030;
  color: #f8bebe;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.8125rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-hero-primary:hover {
  background: #1a1a1a;
  border-color: #1a1a1a;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(48, 48, 48, 0.2);
}

.btn-hero-primary svg {
  transition: transform 0.2s ease;
}

.btn-hero-primary:hover svg {
  transform: translateX(4px);
}

.hero-features {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0;
  padding: 1.5rem 0;
  border-top: 1px solid #e5e5e5;
  border-bottom: 1px solid #e5e5e5;
}

.hero-feature-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0 1.25rem;
  font-size: 0.8125rem;
  color: #888;
}

.hero-feature-item svg {
  width: 18px;
  height: 18px;
  color: #d97706;
  stroke-width: 1.5;
}

.feature-divider {
  width: 1px;
  height: 20px;
  background: #e5e5e5;
}

/* Section Title */
.section-title {
  font-family: 'PingFang SC', 'Noto Sans SC', sans-serif;
  font-size: clamp(1.75rem, 4vw, 2.25rem);
  font-weight: 600;
  color: #1a1a1a;
  text-align: center;
  margin: 0 0 3rem;
  position: relative;
}

.section-title::after {
  content: '';
  display: block;
  width: 60px;
  height: 3px;
  background: #d97706;
  margin: 1rem auto 0;
}

/* Users Section - Tab Style */
.users-section {
  padding: 5rem 0;
  background: white;
  border-top: 1px solid #e5e5e5;
  border-bottom: 1px solid #e5e5e5;
}

.target-tabs {
  display: flex;
  justify-content: center;
  gap: 0;
  margin-bottom: 2.5rem;
  border: 1px solid #303030;
}

.tab-btn {
  flex: 1;
  padding: 1rem 2rem;
  background: transparent;
  border: none;
  border-right: 1px solid #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.8125rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #666;
  cursor: pointer;
  outline: none;
}

.tab-btn:last-child {
  border-right: none;
}

.tab-btn:hover {
  background: rgba(48, 48, 48, 0.05);
  color: #303030;
}

.tab-btn.active {
  background: #303030;
  color: #f8bebe;
}

.target-content {
  max-width: 600px;
  margin: 0 auto;
}

.target-card {
  text-align: center;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes glow-pulse {
  0%, 100% {
    text-shadow: 
      0 0 10px rgba(255, 255, 255, 0.8),
      0 0 20px rgba(255, 255, 255, 0.5),
      0 0 30px rgba(255, 255, 255, 0.3);
  }
  50% {
    text-shadow: 
      0 0 15px rgba(255, 255, 255, 1),
      0 0 30px rgba(255, 255, 255, 0.7),
      0 0 45px rgba(255, 255, 255, 0.5);
  }
}

.target-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #303030;
  color: #303030;
}

.target-card h3 {
  font-family: 'PingFang SC', 'Noto Sans SC', sans-serif;
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0 0 1rem;
  color: #1a1a1a;
}

.target-card p {
  font-size: 1rem;
  line-height: 1.8;
  color: #666;
  margin: 0 0 1.5rem;
}

/* Scenarios Section */
.scenarios-section {
  padding: 5rem 0;
  background: #f5f5f5;
}

.scenarios-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
}

.scenario-card {
  padding: 2rem;
  background: white;
  border: 1px solid #e5e5e5;
  transition: all 0.2s ease;
}

.scenario-card:hover {
  border-color: #303030;
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

.scenario-num {
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 2.5rem;
  font-weight: 600;
  color: rgba(217, 119, 6, 0.15);
  margin-bottom: 1rem;
}

.scenario-card h3 {
  font-family: 'PingFang SC', 'Noto Sans SC', sans-serif;
  font-size: 1.125rem;
  font-weight: 600;
  margin: 0 0 0.75rem;
  color: #1a1a1a;
}

.scenario-card p {
  font-size: 0.875rem;
  line-height: 1.7;
  color: #666;
  margin: 0;
}

/* Footer */
.homepage-footer {
  padding: 2rem 0;
  border-top: 1px solid #e5e5e5;
  background: white;
}

.homepage-footer .section-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-brand {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.footer-logo {
  font-family: 'Plaak-CondensedBold', sans-serif;
  font-size: 1.25rem;
  font-weight: 400;
  color: #303030;
}

.footer-tagline {
  font-size: 0.75rem;
  color: #999;
}

.footer-copy {
  font-size: 0.75rem;
  color: #999;
}

/* Responsive */
@media (max-width: 1024px) {
  .scenarios-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .hero {
    min-height: auto;
    padding: 4rem 1.5rem 3rem;
  }

  .hero-features {
    flex-direction: column;
    gap: 1rem;
    padding: 1rem 0;
  }

  .hero-feature-item {
    padding: 0.5rem 0;
  }

  .feature-divider {
    width: 40px;
    height: 1px;
  }

  .target-tabs {
    flex-direction: column;
    border: none;
  }

  .tab-btn {
    border: 1px solid #303030;
    border-right: none;
    margin-bottom: 0.5rem;
  }

  .tab-btn:last-child {
    margin-bottom: 0;
  }

  .scenarios-grid {
    grid-template-columns: 1fr;
  }

  .homepage-footer .section-inner {
    flex-direction: column;
    gap: 1rem;
    text-align: center;
  }
}

@media (max-width: 480px) {
  .btn-hero-primary {
    width: 100%;
    justify-content: center;
  }
}
</style>
