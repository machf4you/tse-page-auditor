import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const http = axios.create({ baseURL: API, timeout: 60000 });

export const auditApi = {
  run:    (payload)   => http.post("/audit", payload).then(r => r.data),
  list:   ()          => http.get("/audits").then(r => r.data),
  get:    (id)        => http.get(`/audits/${id}`).then(r => r.data),
  delete: (id)        => http.delete(`/audits/${id}`).then(r => r.data),
};
