library(shiny)
library(bs4Dash)
library(shinymanager)
library(shinyjs)
library(dbplyr)
library(dplyr) 
library(DBI)
library(pool)
library(RPostgreSQL)
library(ini)
library(shinyWidgets) 
library(shinycssloaders)
library(highcharter)
library(data.table)
library(shinyscreenshot)
library(xts)
library(reactable)
library(sortable)
library(ggplot2)
library(R6)
library(dplyr)
library(data.table)
library(caTools)
library(RPostgreSQL)

library(DT)
library(shiny)
library(bs4Dash)
library(shinymanager)
library(shinyjs)
library(dbplyr)
library(dplyr) 
library(DBI)
library(pool)
library(RPostgreSQL)
library(ini)
library(shinyWidgets) 
library(shinycssloaders)
library(highcharter)
library(data.table)
library(shinyscreenshot)
library(xts)
library(reactable)
library(sortable)

for(lf in list.files('./utils/',full.names = T, recursive = T)){
  source(lf)
}

calchist <- CalculatorHistory$new()

calchist$process_history(
  operator = "s7",
  aircraft_type = "B737-800",
  min_flight_datetime = as.Date('2022-10-01'),
  max_flight_datetime = as.Date('2023-06-01'),
  ata_code = c("206","207","209"),
  flight_phase = "TAKEOFF",
  parameter_name = "EGTHDM"
)

engine_id <- unique(calchist$df$engine_id)[5]
maint_datetime <- calchist$df$maint_datetime[
  !is.na(calchist$df$maint_datetime) & 
    calchist$df$engine_id == engine_id
    ][1]

df_s <- calchist$df[
  calchist$df$engine_id == engine_id,c(
  "flight_datetime",
  "float_value",
  "float_value_smooth",
  "float_value_smooth_custom",
  "mean_float_value_custom_before_wash",
  "mean_float_value_after_wash_series"
)]
df_e <- calchist$df[
  calchist$df$engine_id == engine_id & calchist$df$event == 1,c(
  "flight_datetime",
  "maint_datetime",
  "time_loss_of_efficiency",
  "ata_code",
  "reason",
  "color"
)]

for(col in c(
  "float_value",
  "float_value_smooth",
  "float_value_smooth_custom",
  "mean_float_value_custom_before_wash",
  "mean_float_value_after_wash_series"
)){
  
  df_s[,col] <- round(df_s[,col],2)
  
}


df_esn <- df_s
df_wash <- df_e

df_s$flight_datetime <- datetime_to_timestamp(df_s$flight_datetime)
df_e$flight_datetime <- datetime_to_timestamp(df_e$flight_datetime)
df_e$time_loss_of_efficiency <- datetime_to_timestamp(df_e$time_loss_of_efficiency)

hc <- highchart() %>%
  hc_add_series(
    name = "egtm",
    id = "raw",
    type = "scatter",
    color = "#7cb5ec50",
    df_s,
    hcaes(
      x = flight_datetime,
      y = float_value
    )
  ) %>%
  hc_add_series(
    name = "egtm smooth",
    id = "smooth",
    type = "line",
    color = "#7cb5ec70",
    df_s,
    hcaes(
      x = flight_datetime,
      y = float_value_smooth
    )
  ) %>%
  hc_add_series(
    name = "egtm smooth custom",
    id = "smooth_custom",
    type = "line",
    color = "#7cb5ec",
    df_s,
    hcaes(
      x = flight_datetime,
      y = float_value_smooth_custom
    )
  ) %>%
  hc_add_series(
    name = "mean egtm before wash",
    df_s, 
    type = "line",
    hcaes(
      x = flight_datetime,
      y = mean_float_value_after_wash_series
    ),
    color = "green"
  ) %>%
  hc_add_series(
    name = "wash",
    tibble::tibble(
      date = df_e$flight_datetime,
      title = df_e$ata_code,
      text = df_e$reason
    ),
    hcaes(
      x = date,
      text = text
    ),
    color = "green",
    type = "flags",
    onSeries = "smooth_custom"
  )

plot_obj <- list()

for(i in 1:nrow(df_e)){
  plot_obj[[i]] <- list(
    label = list(
      text = df_e$ata_code[i]
    ),
    color = "green",
    width = 1,
    value = df_e$flight_datetime[i]
  )
}

for(i in 1:nrow(df_e[!is.na(df_e$time_loss_of_efficiency),])){
  plot_obj[[i + length(plot_obj)]] <- list(
    label = list(
      text = "loss of efficiency"
    ),
    color = "red",
    width = 1,
    value = df_e$time_loss_of_efficiency[which(!is.na(df_e$time_loss_of_efficiency))[i]]
  )
}


hc <- hc %>%
  hc_xAxis(
    plotLines = plot_obj,
    type = 'datetime'
  )

hc
