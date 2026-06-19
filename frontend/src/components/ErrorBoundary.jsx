import React from 'react';

/**
 * ErrorBoundary — catches render errors and displays a fallback UI
 * instead of white-screening the entire app.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <App />
 *   </ErrorBoundary>
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  handleDismiss = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <div className="error-boundary-icon">⚠️</div>
          <h2 className="error-boundary-title">Something went wrong</h2>
          <p className="error-boundary-message">
            {this.state.error?.message || 'An unexpected error occurred.'}
          </p>
          {this.state.errorInfo?.componentStack && (
            <details className="error-boundary-details">
              <summary>Stack trace</summary>
              <pre>{this.state.errorInfo.componentStack}</pre>
            </details>
          )}
          <div className="error-boundary-actions">
            <button className="error-boundary-btn" onClick={this.handleDismiss}>
              Try Again
            </button>
            <button
              className="error-boundary-btn error-boundary-btn-primary"
              onClick={this.handleReload}
            >
              Reload App
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
