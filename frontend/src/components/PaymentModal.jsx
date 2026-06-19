import React, { useState, useEffect, useRef } from 'react';
import { X, Zap, Check, Loader, CreditCard, DollarSign } from 'lucide-react';

const PACKS = [
  {
    id: 'starter',
    name: 'Starter Pack',
    price_usd: 5.00,
    credits: 500,
    features: ['~450 Flash chats', 'Credit/Debit, PayPal, BTC', 'No expiration'],
  },
  {
    id: 'plus',
    name: 'Plus Pack',
    price_usd: 20.00,
    credits: 2500,
    features: ['~2,250 Flash chats', 'Priority speed', 'No expiration'],
  },
  {
    id: 'pro',
    name: 'Pro Pack',
    price_usd: 75.00,
    credits: 10000,
    features: ['~9,000 Flash chats', 'Priority speed', 'No expiration'],
  },
  {
    id: 'enterprise',
    name: 'Enterprise Pack',
    price_usd: 300.00,
    credits: 50000,
    features: ['~45,000 Flash chats', 'Dedicated support', 'No expiration'],
  },
];

export default function PaymentModal({ onClose }) {
  const [selectedPack, setSelectedPack] = useState('starter');
  const [paymentMethod, setPaymentMethod] = useState('stripe'); // stripe | paypal | btcpay
  const [balance, setBalance] = useState(0);
  const [invoice, setInvoice] = useState(null);
  const [status, setStatus] = useState('idle'); // idle | pending | paid | error
  const [error, setError] = useState('');
  const pollRef = useRef(null);

  // Fetch current credit balance
  const fetchBalance = async () => {
    try {
      const res = await fetch('/api/payments/balance');
      if (res.ok) {
        const data = await res.json();
        setBalance(data.credits || 0);
      }
    } catch (err) {
      console.error('Failed to fetch balance', err);
    }
  };

  useEffect(() => {
    fetchBalance();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handlePurchase = async () => {
    setError('');
    setStatus('pending');
    setInvoice(null);

    const pack = PACKS.find(p => p.id === selectedPack);
    if (!pack) return;

    try {
      let endpoint = '';
      let bodyPayload = { pack_id: selectedPack };

      if (paymentMethod === 'stripe') {
        endpoint = '/api/payments/stripe/checkout';
        bodyPayload.redirect_url = window.location.origin;
      } else if (paymentMethod === 'paypal') {
        endpoint = '/api/payments/paypal/create-order';
      } else if (paymentMethod === 'btcpay') {
        endpoint = '/api/payments/btcpay/invoice';
        bodyPayload.redirect_url = window.location.origin;
      }

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyPayload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'Failed to create payment session');
      }

      setInvoice(data);

      const invoiceId = data.session_id || data.order_id || data.invoice_id || data.id;

      // For Stripe and BTCPay, we open the external link in a new window/tab
      if (data.checkout_url || data.payment_url) {
        window.open(data.checkout_url || data.payment_url, '_blank');
      }

      startPolling(invoiceId);
    } catch (err) {
      setError(err.message || 'Purchase checkout failed');
      setStatus('error');
    }
  };

  const startPolling = (invoiceId) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/payments/invoice/${invoiceId}`);
        const data = await res.json();
        if (!res.ok) return;
        const s = (data.status || '').toLowerCase();
        if (s === 'paid' || s === 'confirmed' || s === 'complete' || s === 'completed') {
          setStatus('paid');
          fetchBalance(); // Refresh balance
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (err) {
        // keep polling silently
      }
    }, 4000);
  };

  return (
    <div className="payment-modal-overlay" onClick={onClose}>
      <div className="payment-modal" onClick={(e) => e.stopPropagation()}>
        <button className="payment-close" onClick={onClose}>
          <X size={20} />
        </button>
        <h2 className="payment-title">
          <DollarSign size={22} /> Buy Credit Packs
        </h2>

        <div style={{
          background: 'var(--bg-glass-hover)',
          padding: '10px 15px',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--border-glass)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '14px',
        }}>
          <span>Your Balance:</span>
          <strong>{balance} Credits (${(balance / 100).toFixed(2)})</strong>
        </div>

        {error && <div className="payment-error">{error}</div>}

        <div className="payment-plans">
          {PACKS.map((pack) => (
            <div
              key={pack.id}
              className={`payment-plan-card ${selectedPack === pack.id ? 'selected' : ''}`}
              onClick={() => status !== 'pending' && setSelectedPack(pack.id)}
            >
              <div className="payment-plan-header">
                <span className="payment-plan-name">{pack.name}</span>
                <Zap size={16} className="payment-plan-zap" style={{ color: selectedPack === pack.id ? 'var(--accent-primary)' : 'var(--text-muted)' }} />
              </div>
              <div className="payment-plan-price">${pack.price_usd.toFixed(2)}</div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 'bold' }}>
                {pack.credits} Credits
              </div>
              <ul className="payment-features" style={{ margin: 0, padding: 0 }}>
                {pack.features.map((f, i) => (
                  <li key={i} style={{ fontSize: '11px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <Check size={10} /> {f}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div style={{ marginTop: '10px' }}>
          <label className="settings-field-label">Select Payment Method</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginTop: '5px' }}>
            <button
              type="button"
              onClick={() => setPaymentMethod('stripe')}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '8px',
                padding: '10px',
                borderRadius: 'var(--radius-md)',
                background: paymentMethod === 'stripe' ? 'var(--bg-glass-hover)' : 'var(--bg-glass)',
                border: paymentMethod === 'stripe' ? '2px solid var(--accent-primary)' : '1px solid var(--border-glass)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}
            >
              <CreditCard size={20} />
              <span style={{ fontSize: '12px' }}>Stripe (Cards)</span>
            </button>
            <button
              type="button"
              onClick={() => setPaymentMethod('paypal')}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '8px',
                padding: '10px',
                borderRadius: 'var(--radius-md)',
                background: paymentMethod === 'paypal' ? 'var(--bg-glass-hover)' : 'var(--bg-glass)',
                border: paymentMethod === 'paypal' ? '2px solid var(--accent-primary)' : '1px solid var(--border-glass)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}
            >
              <span style={{ fontSize: '20px', lineHeight: 1 }}>🅿️</span>
              <span style={{ fontSize: '12px' }}>PayPal</span>
            </button>
            <button
              type="button"
              onClick={() => setPaymentMethod('btcpay')}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '8px',
                padding: '10px',
                borderRadius: 'var(--radius-md)',
                background: paymentMethod === 'btcpay' ? 'var(--bg-glass-hover)' : 'var(--bg-glass)',
                border: paymentMethod === 'btcpay' ? '2px solid var(--accent-primary)' : '1px solid var(--border-glass)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}
            >
              <span style={{ fontSize: '20px', lineHeight: 1 }}>⚡</span>
              <span style={{ fontSize: '12px' }}>Bitcoin / Crypto</span>
            </button>
          </div>
        </div>

        <button
          onClick={handlePurchase}
          disabled={status === 'pending'}
          className="settings-save-btn"
          style={{ width: '100%', marginTop: '15px', padding: '12px', justifyContent: 'center' }}
        >
          {status === 'pending' ? (
            <>
              <Loader size={18} className="spin" />
              <span style={{ marginLeft: '10px' }}>Redirecting to checkout...</span>
            </>
          ) : (
            'Purchase Credits'
          )}
        </button>

        {status === 'pending' && invoice && (
          <div className="payment-status payment-pending" style={{ marginTop: '10px', padding: '10px', background: 'var(--bg-glass-hover)', border: '1px solid var(--border-glass)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Loader size={16} className="spin" />
              <strong>Payment Pending...</strong>
            </div>
            <p style={{ fontSize: '12px', margin: '5px 0 0 0', color: 'var(--text-secondary)' }}>
              Order/Invoice ID: {invoice.session_id || invoice.order_id || invoice.invoice_id || invoice.id}
            </p>
            {(invoice.checkout_url || invoice.payment_url) && (
              <a
                href={invoice.checkout_url || invoice.payment_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontSize: '12px', display: 'block', marginTop: '5px', color: 'var(--accent-primary)', fontWeight: 'bold' }}
              >
                Click here if the payment page did not open automatically.
              </a>
            )}
          </div>
        )}

        {status === 'paid' && (
          <div className="payment-status payment-paid" style={{ marginTop: '10px', padding: '12px', background: 'rgba(16, 185, 129, 0.15)', border: '1px solid var(--success)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Check size={20} style={{ color: 'var(--success)' }} />
            <div>
              <strong>Payment Successful!</strong>
              <p style={{ fontSize: '12px', margin: '3px 0 0 0' }}>Your account has been credited.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
