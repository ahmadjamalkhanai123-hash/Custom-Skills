# syntax=docker/dockerfile:1
# Production Java Dockerfile — Maven + Distroless JRE
# Tier 3+ pattern | Target: <120MB final image
# Usage: docker build -t myapp:latest .

ARG JAVA_VERSION=21

# ============================================================
# Stage 1: Build with Maven
# ============================================================
FROM eclipse-temurin:${JAVA_VERSION}-jdk AS builder

WORKDIR /app

# Cache Maven dependencies
COPY pom.xml ./
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn dependency:go-offline -B

# Build application
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.m2/repository \
    mvn package -DskipTests -B && \
    mv target/*.jar app.jar

# Extract layers for Spring Boot (if applicable)
RUN java -Djarmode=layertools -jar app.jar extract --destination /extracted || true

# ============================================================
# Stage 2: Custom JRE with jlink (optional smaller image)
# ============================================================
FROM eclipse-temurin:${JAVA_VERSION}-jdk AS jre-builder

RUN jlink \
    --add-modules java.base,java.logging,java.sql,java.naming,java.net.http,java.security.jgss \
    --strip-debug \
    --no-man-pages \
    --no-header-files \
    --compress=zip-6 \
    --output /custom-jre

# ============================================================
# Stage 3: Production runtime
# ============================================================
FROM gcr.io/distroless/java${JAVA_VERSION}-debian12:nonroot AS production

WORKDIR /app

# Use full JRE (comment out for custom JRE)
COPY --from=builder /app/app.jar ./app.jar

# Uncomment for custom JRE (smaller image):
# COPY --from=jre-builder /custom-jre /opt/java
# ENV PATH="/opt/java/bin:${PATH}"

LABEL org.opencontainers.image.title="{{APP_NAME}}" \
      org.opencontainers.image.version="{{VERSION}}"

EXPOSE 8080

USER nonroot

# JVM tuning for containers
ENV JAVA_OPTS="-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0 -XX:+UseG1GC"

ENTRYPOINT ["java", "-jar", "app.jar"]
