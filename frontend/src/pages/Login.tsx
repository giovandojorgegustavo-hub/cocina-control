export function Login() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm space-y-8">
        <h1 className="text-4xl font-bold text-center text-gray-900">
          Cocina Control
        </h1>

        <form className="space-y-4" aria-label="Formulario de acceso">
          <div className="space-y-2">
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              disabled
              placeholder="operario@cocina.com"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-100 text-gray-400 cursor-not-allowed"
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700"
            >
              Contrasena
            </label>
            <input
              id="password"
              type="password"
              disabled
              placeholder="••••••••"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-100 text-gray-400 cursor-not-allowed"
            />
          </div>

          <button
            type="button"
            disabled
            className="w-full min-h-[48px] bg-gray-300 text-gray-500 font-semibold rounded-lg cursor-not-allowed"
          >
            El login real viene en Frontend #2
          </button>
        </form>
      </div>
    </main>
  )
}
