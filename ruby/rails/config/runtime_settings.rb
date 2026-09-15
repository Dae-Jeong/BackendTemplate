class RuntimeSettings
  ENVIRONMENTS = %w[local test staging production].freeze

  attr_reader :app_name, :environment, :server_host, :server_port

  def self.from_env(env = ENV)
    new(
      app_name: env.fetch("APP_NAME", "Backend Template Rails"),
      environment: env.fetch("APP_ENVIRONMENT", "local"),
      server_host: env.fetch("SERVER_HOST", "127.0.0.1"),
      server_port: integer(env.fetch("SERVER_PORT", "18088"), "SERVER_PORT")
    )
  end

  def self.integer(value, name)
    Integer(value, 10)
  rescue ArgumentError
    raise ArgumentError, "#{name} must be an integer"
  end

  def initialize(app_name:, environment:, server_host:, server_port:)
    raise ArgumentError, "APP_NAME must not be blank" if app_name.strip.empty?
    raise ArgumentError, "APP_ENVIRONMENT is unsupported" unless ENVIRONMENTS.include?(environment)
    raise ArgumentError, "SERVER_HOST must not be blank" if server_host.strip.empty?
    raise ArgumentError, "SERVER_PORT must be between 1 and 65535" unless (1..65_535).cover?(server_port)

    @app_name = app_name
    @environment = environment
    @server_host = server_host
    @server_port = server_port
    freeze
  end
end
