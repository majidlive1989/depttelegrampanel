import axios from 'axios'

export const api = axios.create({ baseURL: '/api', timeout: 20000 })

export const money = (value) => new Intl.NumberFormat('fa-IR').format(Number(value || 0))
