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

config_list <- read.ini( 
  './config/config.ini',
  encoding = getOption("encoding")
)

pool <- dbPool(
  drv = dbDriver("PostgreSQL"),
  dbname = config_list$PROJECT_DB_ECM_NEW$dbname,
  host =  config_list$PROJECT_DB_ECM_NEW$host,
  port = config_list$PROJECT_DB_ECM_NEW$port,
  user = config_list$PROJECT_DB_ECM_NEW$user,
  password = config_list$PROJECT_DB_ECM_NEW$psw
)

fleetsummary <- pool %>%
  tbl(in_schema("ecmapp", "_fleetsummary")) %>%
  filter(
    operator == !!"s7",
    engine_family == !!"CFM56-7"
  ) %>%
  collect()

maintenance <- pool %>%
  tbl(in_schema("ecmapp", "maintenance")) %>%
  filter(
    engine_id %in% !!unique(fleetsummary$engine_id),
    maint_datetime >= !!as.Date('2022-10-01'),
    maint_datetime <= !!as.Date('2023-06-01')
  ) %>%
  collect()

engine_raw_output <- pool %>%
  tbl(in_schema("ecmapp", "engine_raw_output_mv")) %>%
  filter(
    engine_id %in% !!unique(fleetsummary$engine_id), 
    parameter_name == !!"EGTHDM",
    flight_phase == !!"TAKEOFF",
    flight_datetime >= !!as.Date('2022-10-01'),
    flight_datetime <= !!as.Date('2023-06-01')
  ) %>%
  collect()

engine_smooth <- pool %>%
  tbl(in_schema("s7_mdb", "engine_smooth")) %>%
  filter(
    aircraft_id %in% !!unique(fleetsummary$aircraft_id), 
    parameter_name == !!"EGTHDM",
    flight_phase == !!"TAKEOFF",
    flight_datetime >= !!as.Date('2022-10-01'),
    flight_datetime <= !!as.Date('2023-06-01')
  ) %>%
  collect()

maintenance <- maintenance[maintenance$engine_id %in% unique(engine_raw_output$engine_id),]


###
# Calculate df_series, df_events
###

engine_raw_output <- engine_raw_output[
  ,setdiff(
    colnames(engine_raw_output),
    c(
      "integer_value",
      "char_value",
      "parameter_name"
    )
  )]

engine_smooth <- engine_smooth[
  ,setdiff(
    colnames(engine_raw_output),
    c(
      "engine_id"
    )
  )]

engine_raw_output <- engine_raw_output[
  !duplicated(engine_raw_output),
  ]
engine_smooth <- engine_smooth[
  !duplicated(engine_smooth),
  ]

df_series <- engine_raw_output %>%
  left_join(
    engine_smooth,
    by = c(
      "aircraft_id" = "aircraft_id",
      "engine_position" = "engine_position",
      "flight_phase" = "flight_phase",
      "flight_datetime" = "flight_datetime"
    )
  )

colnames(df_series)[
  colnames(df_series) == "float_value.x"
] <- "egthdm"

colnames(df_series)[
  colnames(df_series) == "float_value.y"
  ] <- "egthdm_sage_smooth"


df_events <- maintenance[
  maintenance$ata_code %in% c("206","207","209"),
  setdiff(
    colnames(maintenance),
    c(
      "ata_classification",
      "family",
      "author",
      "creation_datetime"
    )
  )
]

###
# Calculate Mean before and after wash
###

df_series$maint_datetime <- NA
df_series$ata_code <- NA
df_series$reason <- NA
df_series$flight_datetime_loss_of_efficiency <- as.POSIXct(NA)
df_series$mean_egthdm_before_wash_30 <- NA
df_series$mean_egthdm_after_wash_30 <- NA
df_series$mean_egthdm_sage_smooth_before_wash_30 <- NA
df_series$mean_egthdm_sage_smooth_after_wash_30 <- NA

df_events$flight_datetime_loss_of_efficiency <- as.POSIXct(NA)
df_events$flight_datetime_before_wash <- as.POSIXct(NA)
df_events$flight_datetime_after_wash <- as.POSIXct(NA)
df_events$mean_egthdm_before_wash_30 <- NA
df_events$mean_egthdm_after_wash_30 <- NA
df_events$mean_egthdm_sage_smooth_before_wash_30 <- NA
df_events$mean_egthdm_sage_smooth_after_wash_30 <- NA

df_series <- df_series[with(df_series, order(engine_id, flight_datetime)),]

for(i in 1:nrow(df_events)){
  
  df_events$flight_datetime_before_wash[i] <- max(df_series$flight_datetime[
    df_series$engine_id == df_events$engine_id[i] & 
    df_series$flight_datetime <= df_events$maint_datetime[i]
  ], na.rm = TRUE)
  
  df_events$flight_datetime_after_wash[i] <- min(df_series$flight_datetime[
    df_series$engine_id == df_events$engine_id[i] & 
    df_series$flight_datetime > df_events$maint_datetime[i] 
  ], na.rm = TRUE)
  
  
  df_events$mean_egthdm_before_wash_30[i] <- mean(
    tail(
      df_series$egthdm[
        df_series$engine_id == df_events$engine_id[i] & 
          df_series$flight_datetime <= df_events$maint_datetime[i]
      ],
      30
    )
  )
  
  df_events$mean_egthdm_after_wash_30[i] <- mean(
    head(
      df_series$egthdm[
        df_series$engine_id == df_events$engine_id[i] & 
          df_series$flight_datetime > df_events$maint_datetime[i]
        ],
      30
    )
  )
  
  df_events$mean_egthdm_sage_smooth_before_wash_30[i] <- mean(
    tail(
      df_series$egthdm_sage_smooth[
        df_series$engine_id == df_events$engine_id[i] & 
          df_series$flight_datetime <= df_events$maint_datetime[i]
        ],
      30
    )
  )
  
  df_events$mean_egthdm_sage_smooth_after_wash_30[i] <- mean(
    head(
      df_series$egthdm_sage_smooth[
        df_series$engine_id == df_events$engine_id[i] & 
          df_series$flight_datetime > df_events$maint_datetime[i]
        ],
      30
    )
  )
  
  df_series$maint_datetime[
    df_series$engine_id == df_events$engine_id[i] & 
      df_series$flight_datetime == df_events$flight_datetime_after_wash[i]
    ] <- df_events$maint_datetime[i]
  
  df_series$ata_code[
    df_series$engine_id == df_events$engine_id[i] & 
      df_series$flight_datetime == df_events$flight_datetime_after_wash[i]
    ] <- df_events$ata_code[i]
  
  df_series$reason[
    df_series$engine_id == df_events$engine_id[i] & 
      df_series$flight_datetime == df_events$flight_datetime_after_wash[i]
    ] <- df_events$reason[i]
  
}

for(i in which(!is.na(df_series$maint_datetime))){
  # browser()
  if(!is.na(df_events$mean_egthdm_before_wash_30[
    df_events$engine_id == df_series$engine_id[i] &
    df_events$maint_datetime == df_series$maint_datetime[i]
    ])){
    
    df_series$mean_egthdm_before_wash_30[(i-30):(i-1)] <- df_events$mean_egthdm_before_wash_30[
      df_events$engine_id == df_series$engine_id[i] &
        df_events$maint_datetime == df_series$maint_datetime[i]
      ]
    
  }

  df_series$mean_egthdm_after_wash_30[i:min(c(i+30, nrow(df_series)))] <- df_events$mean_egthdm_after_wash_30[
    df_events$engine_id == df_series$engine_id[i] &
      df_events$maint_datetime == df_series$maint_datetime[i]
    ]
  
  if(!is.na(df_events$mean_egthdm_sage_smooth_before_wash_30[
    df_events$engine_id == df_series$engine_id[i] &
    df_events$maint_datetime == df_series$maint_datetime[i]
    ])){
    
    df_series$mean_egthdm_sage_smooth_before_wash_30[(i-30):(i-1)] <- df_events$mean_egthdm_sage_smooth_before_wash_30[
      df_events$engine_id == df_series$engine_id[i] &
        df_events$maint_datetime == df_series$maint_datetime[i]
      ]
    
  }

  df_series$mean_egthdm_sage_smooth_after_wash_30[i:min(c(i+30, nrow(df_series)))] <- df_events$mean_egthdm_sage_smooth_after_wash_30[
    df_events$engine_id == df_series$engine_id[i] &
      df_events$maint_datetime == df_series$maint_datetime[i]
    ]
  
}


df_events$delta_egthdm_wash_30 <- df_events$mean_egthdm_after_wash_30 - df_events$mean_egthdm_before_wash_30
df_events$delta_egthdm_sage_smooth_wash_30 <- df_events$mean_egthdm_sage_smooth_after_wash_30 - df_events$mean_egthdm_before_wash_30

###
# Calculate time loss of efficiency
###

df_series$process_event <- 0

df_series$process_event[!is.na(df_series$maint_datetime)] <- 1

df_series$process_event[diff(df_series$flight_datetime, units = "mins")/(60*24) >= 74] <- 1

df_series$process_interval <- 0



df_events %>%
  group_by(
    ata_code
  ) %>%
  summarise(
    count_washes = n(),
    mean_delta_egthdm_wash_30 = mean(delta_egthdm_wash_30, na.rm = T),
    mean_delta_egthdm_sage_smooth_wash_30 = mean(delta_egthdm_sage_smooth_wash_30, na.rm = T)
  )

# ggplot(
#   data = df_events,
#   aes(
#     x = delta_egthdm_sage_smooth_wash_30,
#     fill = ata_code
#   )
# ) + 
#   geom_histogram(alpha = 0.25) + 
#   theme_minimal()
  

ggplot(
  data = df_events,
  aes(
    x = ata_code,
    y = delta_egthdm_sage_smooth_wash_30,
    color = ata_code
  )
) + 
  geom_violin(alpha = 0.25) + 
  geom_jitter() +
  theme_minimal()

ggplot_list <- list()

for(engine_id in unique(df_events$engine_id)){
  
  df_s <- df_series[df_series$engine_id == engine_id,]
  df_e <- df_events[df_events$engine_id == engine_id,]
  browser()
  ggplot_list[[engine_id]] <- ggplot() + 
    geom_point(
      data = df_s, 
      aes(
        x = flight_datetime, 
        y = egthdm
      ), 
      size=2, 
      alpha=0.1
    ) + 
    geom_line(
      data = df_s,
      aes(
        x = flight_datetime, 
        y = egthdm_sage_smooth
      ),
      alpha=0.4
    ) + 
    geom_line(
      data = df_s,
      aes(
        x = flight_datetime, 
        y = mean_egthdm_sage_smooth_before_wash_30
      ),
      color='red'
    ) + 
    geom_line(
      data = df_s,
      aes(
        x = flight_datetime, 
        y = mean_egthdm_sage_smooth_after_wash_30
      ),
      color='red'
    ) +
    sapply(
      df_e$maint_datetime[df_e$ata_code == "206"], 
      function(xint) geom_vline(
        aes(
          xintercept = xint,
          color = "206"
        )
      )
    ) + 
    sapply(
      df_e$maint_datetime[df_e$ata_code == "207"], 
      function(xint) geom_vline(
        aes(
          xintercept = xint,
          color = "207"
        )
      )
    ) + 
    sapply(
      df_e$maint_datetime[df_e$ata_code == "209"], 
      function(xint) geom_vline(
        aes(
          xintercept = xint,
          color = "209"
        )
      )
    ) + 
    geom_vline(
      data = df_s[df_s$process_event == 1,],
      aes(
        xintercept = flight_datetime,
        color = 'red'
      )
    ) +
    ggtitle(
      paste0(
        "A/C: ",
        unique(fleetsummary$ac_reg_new[fleetsummary$engine_id == engine_id]),
        ", Pos: ",
        unique(fleetsummary$engine_position[fleetsummary$engine_id == engine_id]),
        ", ESN: ",
        engine_id
      )
    ) +
    scale_color_manual(name='Wash type',
                       breaks=c('206', '207', '209'),
                       values=c('206'="#00AFBB", '207'="#E7B800", '209'="#FC4E07")) +
    theme_minimal()
  
}


