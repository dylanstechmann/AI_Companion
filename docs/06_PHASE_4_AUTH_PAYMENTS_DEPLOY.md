# AI Companion - Phase 4: Auth, Payments, and Deployment

COST TIER: Mid-tier model
COMPLEXITY: Medium
PREREQUISITES: Phase 1-3 core features working

---

## Task 1: User Authentication and Sessions

### Goal
Support multiple users with isolated data (characters, messages, memories).
Each user has their own login, their own characters, and their own chat history.

### Architecture

**Authentication Flow:**
```
User -> Login Page -> POST /api/auth/login -> JWT token
     -> Register    -> POST /api/auth/register -> JWT token
     -> All subsequent requests include: Authorization: Bearer <token>
```

**Session Management:**
- JWT tokens with short expiry (1 hour) + refresh tokens (7 days)
- Tokens stored in httpOnly cookies (more secure than localStorage)
- Middleware validates JWT on every /api/ route except /auth/*

### Backend Implementation

**New file: backend/app/auth.py**
```
Dependencies: python-jose[cryptography], passlib[bcrypt]

class AuthService:
    async def register(self, email: str, password: str) -> User
    async def login(self, email: str, password: str) -> TokenPair
    async def refresh(self, refresh_token: str) -> TokenPair
    async def get_current_user(self, token: str) -> User
    
def require_auth(request: Request) -> User:
    """FastAPI dependency that extracts and validates the JWT."""
```

**Database changes (database.py):**
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Add user_id foreign key to existing tables:
ALTER TABLE characters ADD COLUMN user_id INTEGER REFERENCES users(id);
ALTER TABLE messages ADD COLUMN user_id INTEGER REFERENCES users(id);
```

**New routes:**
- POST /api/auth/register - Create account
- POST /api/auth/login - Get JWT
- POST /api/auth/refresh - Refresh JWT
- GET /api/auth/me - Current user info
- POST /api/auth/logout - Invalidate refresh token

**Modify all existing routes:**
- Add `user = Depends(require_auth)` dependency
- Filter all queries by user_id
- Characters and messages are per-user

### Frontend Changes

**New components:**
- LoginPage.jsx - Email/password login form
- RegisterPage.jsx - Registration form
- AuthProvider.jsx - React context for auth state

**Auth flow:**
- On app load, check for stored JWT
- If no JWT or expired, show LoginPage
- After login, store JWT in memory (not localStorage for security)
- Add Authorization header to all fetch calls
- On 401 response, redirect to login

---

## Task 2: Bitcoin/Lightning Payment Integration

### Goal
Monetize the platform. Users pay with Bitcoin (on-chain or Lightning Network) for:
- Premium features (better TTS voices, larger context, priority GPU)
- Subscription plans (monthly)
- Pay-per-use (per message or per minute of voice)

### Architecture Options

**Option A: BTCPay Server (Self-Hosted, Recommended)**
- Self-hosted Bitcoin payment processor
- Supports on-chain BTC + Lightning Network
- No third-party fees
- Docker-compatible (add as a service)
- REST API for creating invoices and checking payment status

**Option B: Strike API**
- Hosted Lightning payment processor
- Simple REST API
- Lower setup complexity but third-party dependency

**Option C: LNbits**
- Lightweight Lightning wallet/payment system
- Can run alongside the app
- Good for micropayments

### Backend Implementation (BTCPay Server approach)

**New file: backend/app/payments.py**
```
class PaymentService:
    def __init__(self, btcpay_url: str, api_key: str, store_id: str):
        self.client = httpx.AsyncClient(base_url=btcpay_url)
        self.api_key = api_key
        self.store_id = store_id
    
    async def create_invoice(self, amount_sats: int, description: str) -> Invoice:
        """Create a BTCPay invoice. Returns payment URL and invoice ID."""
    
    async def check_invoice(self, invoice_id: str) -> InvoiceStatus:
        """Check if an invoice has been paid."""
    
    async def handle_webhook(self, payload: dict) -> None:
        """Process BTCPay webhook for payment confirmation."""
        # Update user's balance/subscription in database
    
    async def get_user_balance(self, user_id: int) -> int:
        """Get user's remaining credit in satoshis."""
    
    async def deduct_usage(self, user_id: int, amount_sats: int, reason: str) -> bool:
        """Deduct credits for API usage."""
```

**Database changes:**
```sql
CREATE TABLE payments (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    invoice_id TEXT UNIQUE,
    amount_sats INTEGER,
    status TEXT,  -- pending, paid, expired
    created_at TIMESTAMP,
    paid_at TIMESTAMP
);

CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    plan TEXT,  -- free, basic, premium
    started_at TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN
);

CREATE TABLE usage_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action TEXT,  -- chat_message, tts_generation, image_analysis, code_execution
    cost_sats INTEGER,
    created_at TIMESTAMP
);
```

**New routes:**
- POST /api/payments/invoice - Create payment invoice
- GET /api/payments/invoice/{id} - Check payment status
- POST /api/payments/webhook - BTCPay webhook endpoint
- GET /api/payments/balance - User's current balance
- GET /api/payments/history - Payment history
- GET /api/payments/plans - Available subscription plans

**Pricing Model (example):**
```
Free tier:
- 50 messages/day
- Browser TTS only
- No code execution

Basic (10,000 sats/month):
- 500 messages/day
- Cloud TTS
- Code execution
- Web search

Premium (50,000 sats/month):
- Unlimited messages
- HD TTS voices
- Priority GPU
- Multi-agent
- Browser control
- Custom skills
```

### Frontend Changes

**New components:**
- PricingPage.jsx - Show plans with BTC prices
- PaymentModal.jsx - QR code for Lightning invoice, payment status
- UsageDashboard.jsx - Credits remaining, usage history

**Payment flow:**
1. User selects a plan
2. Frontend creates invoice via POST /api/payments/invoice
3. Shows QR code (Lightning) or on-chain address
4. Polls for payment confirmation
5. On confirmation, updates UI to show premium features

### Docker Changes
If self-hosting BTCPay:
```yaml
# Add to docker-compose.yml
btcpay:
  image: btcpayserver/btcpayserver:latest
  ports:
    - "23000:23000"
  volumes:
    - btcpay_data:/data
  environment:
    BTCPAY_HOST: btcpay.yourdomain.com
    # ... Bitcoin node connection config
```

### Environment Variables
```env
BTCPAY_URL=http://btcpay:23000
BTCPAY_API_KEY=your-btcpay-api-key
BTCPAY_STORE_ID=your-store-id
BTCPAY_WEBHOOK_SECRET=your-webhook-secret
```

---

## Task 3: Production Deployment

### Goal
Deploy the application to a cloud server with GPU, SSL, and proper security.

### Infrastructure
- Cloud provider: RunPod, Vast.ai, or Lambda Labs (GPU instances)
- Reverse proxy: Nginx or Caddy (SSL termination)
- Domain: Configure DNS A record
- SSL: Let's Encrypt via Caddy (automatic)

### docker-compose.production.yml changes
- Remove volume mounts for source code (use COPY instead)
- Add Caddy/Nginx service for SSL
- Set CORS to specific domain instead of *
- Enable rate limiting
- Add health check endpoints for monitoring
- Log aggregation (optional: Loki + Grafana)

### Security Checklist
- [ ] CORS restricted to production domain
- [ ] Rate limiting on all endpoints
- [ ] JWT secret is strong and unique
- [ ] API key is not exposed in frontend
- [ ] Sandbox has no filesystem escape
- [ ] Browser automation is sandboxed
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention (parameterized queries - already done via aiosqlite)
- [ ] XSS prevention (React handles this, but verify dangerouslySetInnerHTML usage)

---

## Acceptance Criteria

### Auth:
- [ ] Users can register and login
- [ ] JWT authentication works on all routes
- [ ] Each user has isolated data
- [ ] Refresh token rotation works

### Payments:
- [ ] Bitcoin Lightning invoices can be created
- [ ] Payment confirmation works via webhook
- [ ] User balance is tracked
- [ ] Usage is metered and deducted
- [ ] Free tier limits are enforced

### Deployment:
- [ ] HTTPS works with valid SSL
- [ ] All services start cleanly
- [ ] Health checks pass
- [ ] Rate limiting is active
