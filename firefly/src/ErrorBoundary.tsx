import React from 'react';

type ErrorBoundaryState = { hasError: boolean; message?: string };

export class ErrorBoundary extends React.Component<React.PropsWithChildren<{}>, ErrorBoundaryState> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    // In real app, send to logging service
    // console.error('ErrorBoundary caught error', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 16 }}>
          <h2>Something went wrong.</h2>
          <p>{this.state.message || 'Unexpected error'}</p>
        </div>
      );
    }

    return this.props.children as React.ReactElement;
  }
}


