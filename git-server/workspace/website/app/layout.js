import { Comfortaa } from 'next/font/google'
import './globals.css'

const comfortaa = Comfortaa({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-comfortaa',
})

export const metadata = {
  title: 'CyberFun Tech',
  description: 'Professional animatronic control systems built in Python.',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={comfortaa.variable}>
      <body className={comfortaa.className}>{children}</body>
    </html>
  )
}
