import axios from 'axios';

const API_URL =
  (process.env.REACT_APP_API_URL as string | undefined) ||
  `${window.location.protocol}//${window.location.hostname}:8000`;

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

export { API_URL };
