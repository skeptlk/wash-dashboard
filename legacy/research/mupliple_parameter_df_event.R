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

start <- Sys.time()

calchist <- CalculatorHistory_v2$new()

params <- data.frame(
  parameter_name = c("GWFM","DEGT","EGTHDM"),
  flight_phase = c("CRUISE","CRUISE","TAKEOFF"),
  smooth_window = c(30,30,30),
  number_of_obs_mean = c(15,15,15),
  threshhold = c(0.05,2,2),
  cartoonist = c(-1,-1,1)
)

list_calchist_df <- list()
list_calchist_df_event <- list()

for(i in 1:nrow(params)){
  
  calchist$process_history(
    operator = "s7",
    aircraft_type = "B737-800", #"A320-200"
    min_flight_datetime = as.Date('2022-10-01'),
    max_flight_datetime = as.Date('2023-06-01'),
    ata_code = c("206","207","209"),
    flight_phase = params$flight_phase[i],
    parameter_name = params$parameter_name[i],  #"GWFM", # "DEGT",
    smooth_window = params$smooth_window[i],
    number_of_obs_mean = params$number_of_obs_mean[i],
    threshhold = params$threshhold[i],
    cartoonist = params$cartoonist[i]
  )
  
  list_calchist_df[[as.character(i)]] <- calchist$df
  
  df_event <- calchist$df_event[,c(
    "ac_reg_new",
    "engine_position",
    "engine_id",
    "maint_datetime",
    "ata_code",
    "delta_float_value_custom",
    "mean_float_value_custom_before_wash",
    "mean_float_value_custom_after_wash",
    "time_loss_of_efficiency",
    # "departures",
    # "arrivals",
    # "flights",
    "cyc_loss_off_efficiency",
    "hrs_loss_off_efficiency"
  )]
  
  df_event <- df_event[!is.na(df_event$delta_float_value_custom),]
  df_event$maint_datetime <- as.Date(df_event$maint_datetime)
  df_event$time_loss_of_efficiency <- as.Date(df_event$time_loss_of_efficiency)
  df_event$days_loss_of_efficiency <- as.numeric(df_event$time_loss_of_efficiency - df_event$maint_datetime)
  
  for(col in c("delta_float_value_custom",
               "mean_float_value_custom_before_wash",
               "mean_float_value_custom_after_wash",
               "hrs_loss_off_efficiency")){
    df_event[,col] <- round(df_event[,col],2)
    
  }
  
  colnames(df_event)[
    colnames(df_event) == "delta_float_value_custom"
  ] <- paste0(
    "delta_",
    params$parameter_name[i],
    "_",
    params$flight_phase[i]
  )
  
  colnames(df_event)[
    colnames(df_event) == "mean_float_value_custom_before_wash"
    ] <- paste0(
      "mean_",
      params$parameter_name[i],
      "_",
      params$flight_phase[i],
      "_before_wash"
    )
  
  colnames(df_event)[
    colnames(df_event) == "mean_float_value_custom_after_wash"
    ] <- paste0(
      "mean_",
      params$parameter_name[i],
      "_",
      params$flight_phase[i],
      "_after_wash"
    )
  
  colnames(df_event)[
    colnames(df_event) == "time_loss_of_efficiency"
    ] <- paste0(
      "date_loe_",
      params$parameter_name[i],
      "_",
      params$flight_phase[i]
    )
  
  colnames(df_event)[
    colnames(df_event) == "cyc_loss_off_efficiency"
    ] <- paste0(
      "cyc_loe_",
      params$parameter_name[i],
      "_",
      params$flight_phase[i]
    )
  
  colnames(df_event)[
    colnames(df_event) == "hrs_loss_off_efficiency"
    ] <- paste0(
      "hrs_loe_",
      params$parameter_name[i],
      "_",
      params$flight_phase[i]
    )
  
  colnames(df_event)[
    colnames(df_event) == "days_loss_of_efficiency"
    ] <- paste0(
      "days_loe_",
      params$parameter_name[i],
      "_",
      params$flight_phase[i]
    )
  
  list_calchist_df_event[[as.character(i)]] <- df_event
  
}

df_event <- list_calchist_df_event[[as.character(1)]] %>%
  left_join(
    list_calchist_df_event[[as.character(2)]],
    by = c(
      "ac_reg_new" = "ac_reg_new",
      "engine_position" = "engine_position",
      "engine_id" = "engine_id",
      "maint_datetime" = "maint_datetime",
      "ata_code" = "ata_code"
    )
  )%>%
  left_join(
    list_calchist_df_event[[as.character(3)]],
    by = c(
      "ac_reg_new" = "ac_reg_new",
      "engine_position" = "engine_position",
      "engine_id" = "engine_id",
      "maint_datetime" = "maint_datetime",
      "ata_code" = "ata_code"
    )
  )


df_g <- df_event %>%
  group_by(ata_code) %>%
  summarise(
    count_washes = n(),
    count_engines = n_distinct(engine_id),
    mean_delta_GWFM_CRUISE = round(mean(delta_GWFM_CRUISE, na.rm = T),2),
    mean_cyc_loe_GWFM_CRUISE = round(mean(cyc_loe_GWFM_CRUISE, na.rm = T)),
    mean_hrs_loe_GWFM_CRUISE = round(mean(hrs_loe_GWFM_CRUISE, na.rm = T)),
    mean_days_loe_GWFM_CRUISE = round(mean(days_loe_GWFM_CRUISE, na.rm = T))

    ,
    mean_delta_DEGT_CRUISE = round(mean(delta_DEGT_CRUISE, na.rm = T),2),
    mean_cyc_loe_DEGT_CRUISE = round(mean(cyc_loe_DEGT_CRUISE, na.rm = T)),
    mean_hrs_loe_DEGT_CRUISE = round(mean(hrs_loe_DEGT_CRUISE, na.rm = T)),
    mean_days_loe_DEGT_CRUISE = round(mean(days_loe_DEGT_CRUISE, na.rm = T))
    
    ,
    mean_delta_EGTHDM_TAKEOFF = round(mean(delta_EGTHDM_TAKEOFF, na.rm = T),2),
    mean_cyc_loe_EGTHDM_TAKEOFF = round(mean(cyc_loe_EGTHDM_TAKEOFF, na.rm = T)),
    mean_hrs_loe_EGTHDM_TAKEOFF = round(mean(hrs_loe_EGTHDM_TAKEOFF, na.rm = T)),
    mean_days_loe_EGTHDM_TAKEOFF = round(mean(days_loe_EGTHDM_TAKEOFF, na.rm = T))
  )


df_gg <- as.data.frame(
  as.matrix(
    t(
      df_g
    )
  )
)

df_gg$ata_code <- row.names(df_gg)

row.names(df_gg) <- NULL

colnames(df_gg) <- NULL

colnames(df_gg) <- v(df_gg[1,])

end <- Sys.time()

end - start

df_gg

ggplot(
  data = df_event[
    df_event$delta_EGTHDM_TAKEOFF <= 18 & 
      df_event$delta_EGTHDM_TAKEOFF >= 0,],
  aes(
    x = ata_code,
    y = delta_EGTHDM_TAKEOFF,
    color = ata_code
  )
) + 
  geom_violin(alpha = 0.25) + 
  stat_summary(fun = "mean",
               geom = "crossbar",
               aes(color = ata_code)) + 
  geom_jitter() +
  theme_minimal()
