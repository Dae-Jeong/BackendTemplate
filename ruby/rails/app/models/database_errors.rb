module DatabaseErrors
  class Busy < StandardError
  end

  class PoolTimeout < StandardError
  end

  def self.translate
    yield
  rescue ActiveRecord::ConnectionTimeoutError => error
    raise PoolTimeout, cause: error
  rescue ActiveRecord::StatementInvalid => error
    raise Busy, cause: error if sqlite_busy?(error)

    raise
  end

  def self.sqlite_busy?(error)
    cause = error
    while cause
      return true if cause.is_a?(SQLite3::BusyException) || cause.is_a?(SQLite3::LockedException)

      cause = cause.cause
    end
    false
  end
  private_class_method :sqlite_busy?
end
