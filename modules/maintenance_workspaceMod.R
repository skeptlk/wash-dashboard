maintenance_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("maintenance_workspace"))
  
}

maintenance_workspaceMod <- function(input, output, session, credentials, pool) {
  
  ns <- session$ns
  
  output$maintenance_operator <- renderUI({
    
    ns <- session$ns
    
    fleetsummary <- pool %>% tbl(in_schema("ecmapp", "_fleetsummary")) %>% collect()
    
    userdefault_test <- pool %>%
      tbl(in_schema("utair", "userdefault_test")) %>%
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      selected <- unique(fleetsummary$operator)[1]
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi
      
    }
    
    pickerInput(
      ns("maintenance_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator), #"utair",
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected,#"utair",
      multiple = F
    )
    
  })
  
  output$maintenance_actype <- renderUI({
    
    ns <- session$ns
    # browser()
    choices <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      filter(
        operator %in% !!input$maintenance_operator_pi
      ) %>%
      group_by(
        operator,
        aircraft_type
      ) %>%
      summarise(
        count_ac = n_distinct(aircraft_id)
      ) %>%
      collect()
    
    # userdefault_test <- pool %>% 
    #   tbl(in_schema("utair", "userdefault_test")) %>% 
    #   filter(
    #     user %in% !!credentials()$user
    #   ) %>%
    #   collect()
    # 
    # if(nrow(userdefault_test) == 0){
    #   
    #   selected <- choices$aircraft_family[1]
    #   
    # }
    # else{
    #   
    #   selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_actype_pi
    #   
    # }
    
    pickerInput(
      ns("maintenance_actype_pi"),
      label = "A/C Type:", 
      choices = lapply(split(choices$aircraft_type, choices$operator), as.list),
      choicesOpt = list(
        subtext = unlist(lapply(split(choices$count_ac, choices$operator), as.list))
      ), 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = choices$aircraft_type,
      multiple = T
    )
    
  })
  
  output$maintenance_acreg <- renderUI({
    
    ns <- session$ns
    
    choices <- NULL
    
    choicesOpt <- NULL
    
    selected <- NULL
    
    if(!is.null(input$maintenance_actype_pi) & !is.null(input$maintenance_operator_pi)){
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$maintenance_operator_pi,
          aircraft_type %in% !!input$maintenance_actype_pi,
          is.na(removal_datetime),
          !is.na(ac_reg_new),
          ac_reg_new != "-"
        ) %>%
        collect()
      
      fleetsummary <- fleetsummary[!duplicated(fleetsummary),]
      
      fleetsummary <- fleetsummary %>% 
        group_by(
          aircraft_id, 
          engine_position
        ) %>%
        filter(
          install_datetime == max(install_datetime)
        )
      
      df_choices <- fleetsummary[,c(
        "aircraft_type",
        "ac_reg_new",
        "ac_reg_old",
        "aircraft_id",
        "engine_position",
        "engine_id"
      )] %>%
        group_by(
          aircraft_type,
          ac_reg_new,
          ac_reg_old,
          aircraft_id
        ) %>%
        tidyr::pivot_wider(
          names_from = engine_position,
          names_prefix = "esn_",
          values_from = c(
            engine_id
          )
        ) %>%
        mutate(
          subtext = paste0(
            ac_reg_old,
            " ",
            aircraft_id,
            ", pos.1: ",
            esn_1,
            ", pos.2: ",
            esn_2
          )
        )
      
      # userdefault_test <- pool %>% 
      #   tbl(in_schema("utair", "userdefault_test")) %>% 
      #   filter(
      #     user %in% !!credentials()$user
      #   ) %>%
      #   collect()
      # 
      # if(nrow(userdefault_test) == 0){
      #   
      #   selected <- choices$ac_reg_new[1]
      #   
      # }
      # else{
      #   
      #   selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_acreg_pi
      #   
      # }
      
      choices <- lapply(split(df_choices$ac_reg_new, df_choices$aircraft_type), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(df_choices$subtext, df_choices$aircraft_type), as.list))
      )
      
      pickerInput(
        ns("maintenance_acreg_pi"),
        label = "A/C Reg:", 
        choices = choices,
        choicesOpt = choicesOpt, 
        options = list(
          `live-search`=TRUE,
          `actions-box` = TRUE,
          `deselect-all-text` = "deselect",
          `select-all-text` = "select all",
          `none-selected-text` = "zero"
        ),
        selected = df_choices$ac_reg_new,
        multiple = T
      )
      
    }
    
    
  })
  
  maintenance_data <- reactiveValues(
    fleetsummary = NULL,
    atacode = NULL,
    atacodecolor = NULL,
    maintenance = NULL,
    config = NULL
  )
  
  
  observeEvent(input$update_maintenance_data, {
    # browser()
    maintenance_data$fleetsummary <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      filter(
        ac_reg_new %in% !!input$maintenance_acreg_pi
      ) %>%
      collect()
    
    maintenance_data$maintenance <- pool %>%
      tbl(in_schema("ecmapp", "maintenance")) %>%
      filter(
        engine_id %in% !!unique(maintenance_data$fleetsummary$engine_id)
      ) %>%
      collect()
    
    maintenance_data$maintenance <- maintenance_data$maintenance[
      !duplicated(maintenance_data$maintenance)
      ,]
    
    # browser()
    
    maintenance_data$atacodecolor <- pool %>%
      tbl(in_schema("ecmapp", "atacodecolor_operator")) %>%
      filter(
        operator %in% !!input$maintenance_operator_pi
      ) %>%
      collect()
    
  })
  
  output$summary_table <- renderReactable({
    
    req(maintenance_data$maintenance)
    
    if (is.null(maintenance_data$maintenance)){
      return()
    }
    else{
      # browser()
      reactable(
        maintenance_data$maintenance[,setdiff(
          colnames(maintenance_data$maintenance),
          c(
            "ata_classification",
            "family"
          )
        )],
        searchable = TRUE,
        filterable = TRUE,
        showPageInfo = TRUE,
        showPagination = TRUE,
        
        wrap = FALSE,
        resizable = TRUE,
        striped = TRUE, 
        highlight = TRUE,
        groupBy = c(
          "engine_id"
        ),
        columns = list(
          maint_datetime = colDef(aggregate = "max")
          #family = colDef(aggregate = "unique"),
          #creation_datetime = colDef(aggregate = "max")
        ),
        bordered = TRUE
      )
    }
    
  })
  
  output$maintenance_table <- DT::renderDataTable({
    
    req(maintenance_data$maintenance)
    
    if (is.null(maintenance_data$maintenance)){
      return()
    }
    else{
      # browser()
      DT::datatable({
        maintenance_data$maintenance[,setdiff(
          colnames(maintenance_data$maintenance),
          c(
            "ata_classification",
            "family"
          )
        )]
      },
      caption = "Report table",
      extensions = 'Buttons',
      
      options = list(
        dom = 'Bfrtip',
        
        buttons = list(
          list(
            extend = 'collection',  #'csv',
            buttons = c('csv', 'excel'),
            exportOptions = list(
              modifiers = list(page = "all")
            )
          )
        ),
        columnDefs=list(list(className='dt-center',targets="_all")
        ),
        scrollX = TRUE
      ),
      filter = "top",
      selection = 'single',
      class = 'hover', 
      rownames = FALSE
      )
      
    }
    
  })
  
  output$ui_delete_maintenance <- renderUI({
    
    if(!is.null(input$maintenance_table_rows_selected)){
      
      actionBttn(
        ns("delete_maintenance"),
        "Delete maintenance",
        color = "danger"
      )
      
    }
    
  })
  
  observeEvent(input$delete_maintenance,{
    showModal(modal_delete_maintenance)
  })
  
  modal_delete_maintenance <- modalDialog(
    fluidPage(
      h3(
        paste0(
          "Do you really want to delete maintenance action"
        )
      ),
      actionBttn(
        ns("ab_modal_delete_maintenance"), 
        "Delete", 
        color = "danger"
      )
    ),
    size="l"
  )
  
  observeEvent(input$ab_modal_delete_maintenance,{
    # browser()
    row <- maintenance_data$maintenance[
        input$maintenance_table_rows_selected,
      ]
    
    maintenance <- pool %>%
      tbl(in_schema("ecmapp", "maintenance")) %>%
      collect()
    
    maintenance <- maintenance[
      !(maintenance$engine_id == row$engine_id &
          maintenance$maint_datetime== row$maint_datetime &
          maintenance$ata_code== row$ata_code &
          maintenance$reason== row$reason &
          maintenance$author== row$author &
          maintenance$creation_datetime == row$creation_datetime
      ),
    ]
    
    maintenance_data$maintenance <- maintenance_data$maintenance[
      -input$maintenance_table_rows_selected,
    ]
    
    dbWriteTable(pool, c("ecmapp", "maintenance"), value = maintenance, row.names = FALSE, overwrite = TRUE)
    
    removeModal()
    
    showNotification(
      paste0(
        "Maintenance has been deleted"
      )
    )
    
  })
  
  
  observeEvent(input$create_maintenance,{
    
    showModal(
      modal_create_maintenance
    )
    
  })
  
  modal_create_maintenance <- modalDialog(
    fluidPage(
      h3(
        paste0(
          "Please enter maintenance action credits"
        )
      ),
      uiOutput(ns("ui_maintenance_engine_id")),
      dateInput(
        ns("di_maint_datetime"), 
        "Maintenance Date",
        value = as.Date(Sys.Date())
      ),
      uiOutput(ns("ui_maintenance_atacode")),
       textAreaInput(
        ns("ti_maintenance_reason"),
        "Reason"
      ),
      actionBttn(
        ns("ab_save_maintenance"), 
        "Save maintenance action", 
        color = "success"
      )
    ),
    size="l"
  )
  
  output$ui_maintenance_engine_id <- renderUI({
    
    pickerInput(
      ns("pi_maintenance_engine_id"),
      label = "Engine id",
      choices = unique(maintenance_data$fleetsummary$engine_id), 
      options = list(
        `live-search`=TRUE
      ),
      multiple = F
    )
    
  })
  
  output$ui_maintenance_atacode <- renderUI({
    
    if(!is.null(input$pi_maintenance_engine_id)){
      
      pickerInput(
        ns("pi_maintenance_atacode_custom"),
        label = "Ata code",
        choices = maintenance_data$atacodecolor$ata_code,
        choicesOpt = list(
          subtext = maintenance_data$atacodecolor$description
        ), 
        options = list(
          `live-search`=TRUE
        ),
        multiple = F
      ) 
      
    }
    
  })
  
  observeEvent(input$ab_save_maintenance,{
    # browser()
    new_maintenance <- data.frame(
      engine_id = input$pi_maintenance_engine_id,
      maint_datetime = input$di_maint_datetime,
      ata_code = input$pi_maintenance_atacode_custom,
      ata_classification = NA,
      family = NA,
      reason = input$ti_maintenance_reason,
      author = credentials()$user,
      creation_datetime = Sys.time()
    )
    # browser()
    maintenance_data$maintenance <- rbind(
      maintenance_data$maintenance,
      new_maintenance
    )
    
    dbWriteTable(pool, c("ecmapp", "maintenance"), value = new_maintenance, row.names = FALSE, append = TRUE)
    
    removeModal()
    
    showNotification(
      paste0(
        "Maintenance has been created"
      )
    )
    
  })
  
  output$useroptions_maintenance_atacode <- renderUI({
    
    # if(is.null(maintenance_data$atacodecolor)){
    #   
    #   maintenance_data$atacodecolor <- pool %>%
    #     tbl(in_schema("ecmapp", "atacodecolor_operator")) %>%
    #     filter(
    #       operator %in% !!headerselectors$maintenance$maintenance_operator_pi()
    #     )
    #     collect()
    #   
    # }
    
    pickerInput(
      ns("pi_maintenance_atacode"),
      label = "Ata code",
      choices = maintenance_data$atacodecolor$ata_code,
      choicesOpt = list(
        subtext = maintenance_data$atacodecolor$description
      ), 
      options = list(
        `live-search`=TRUE
      ),
      multiple = F,
      width = '200px'
    )
    
  })
  
  output$useroptions_maintenance_color <- renderUI({
    
    colorPickr(
      inputId = ns("cp_maintenance_color"),
      label = "Pick a color (classic theme):",
      selected = "#28a745",
      #selected = maintenance_data$atacodecolor$color[maintenance_data$atacodecolor$ata_code == input$pi_maintenance_atacode],
      width = '200px'
    )
    
  })
  
  output$useroptions_maintenance_params_all <- renderUI({
    
    checkboxInput(
      ns("ci_maintenance_atacodecolor_params_all"),
      "ALL Parameters",
      TRUE
    )
    
  })
  
  output$useroptions_maintenance_params <- renderUI({
    
    selected <- NULL
    
    choices <- NULL
    
    choicesOpt <- NULL
    
    if(!is.null(input$ci_maintenance_atacodecolor_params_all)){
      
      parameters <- pool %>%
        tbl(in_schema("ecmapp", "parameters")) %>%
        filter(
          aircraft_type %in% !!unique(input$maintenance_actype_pi)
        ) %>%
        collect()
      
      parameters <- parameters[!duplicated(parameters[,setdiff(colnames(parameters),c("aircraft_type","flight_phase") )]),]
      # browser()
      parameters$parameter_sort <- 0
      
      parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
      
      parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
      
      parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
      
      parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
      
      parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
      
      parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
      
      choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
      )
      
      if(input$ci_maintenance_atacodecolor_params_all){
        
        selected <- parameters$parameter_name
        
      }
      
    }
    
    pickerInput(
      ns("pi_maintenance_atacodecolor_params"),
      label = "Parameters",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      selected = selected,
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    ) 
    
  })
  
  # observeEvent(input$pi_maintenance_atacode, {
  #   updateColorPickr(
  #     session, 
  #     ns("cp_maintenance_color"), 
  #     maintenance_data$atacodecolor$color[maintenance_data$atacodecolor$ata_code == input$pi_maintenance_atacode]
  #   )
  # })
  
  observeEvent(input$save_atacodecolor,{
    
    showModal(
      modal_save_atacodecolor
    )
    
  })
  
  modal_save_atacodecolor <- modalDialog(
    fluidPage(
      h3(
        paste0(
          "Do you really want to save maintenance colour"
        )
      ),
      actionBttn(
        ns("ab_save_atacodecolor"), 
        "Save settings", 
        color = "success"
      )
    ),
    size="l"
  )
  
  observeEvent(input$ab_save_atacodecolor,{
    
    # browser()
    
    # maintenance_data$atacodecolor$color[
    #   maintenance_data$atacodecolor$ata_code == input$pi_maintenance_atacode
    # ] <- input$cp_maintenance_color
    # 
    # dbWriteTable(
    #   pool, 
    #   c("ecmapp", "atacodecolor"), 
    #   value = maintenance_data$atacodecolor, 
    #   row.names = FALSE,
    #   overwrite = TRUE
    # )
    # 
    # removeModal()
    # 
    # showNotification(
    #   paste0(
    #     "Maintenance settings has been saved"
    #   )
    # )
    # browser()
    maintenance_data$atacodecolor$color[
      maintenance_data$atacodecolor$ata_code == input$pi_maintenance_atacode
      ] <- input$cp_maintenance_color
    
    atacodecolor_all <- pool %>%
      tbl(in_schema("ecmapp", "atacodecolor_operator")) %>%
      collect()
      
    atacodecolor_all[atacodecolor_all$operator == unique(maintenance_data$atacodecolor$operator),] <- maintenance_data$atacodecolor
    
    #maintenance_data$atacodecolor$operator <- headerselectors$maintenance$maintenance_operator_pi()
    
    dbWriteTable(
      pool, 
      c("ecmapp", "atacodecolor_operator"), 
      value = atacodecolor_all, 
      row.names = FALSE,
      overwrite = TRUE
    )
    
    removeModal()
    
    showNotification(
      paste0(
        "Maintenance settings has been saved"
      )
    )
    
  })
  
  
  output$useroptions_maintenance_ata_table <- DT::renderDataTable({
    
    datatable({
      maintenance_data$atacodecolor[with(maintenance_data$atacodecolor,order(ata_code)),]
    },filter = "top",
    selection = 'single',
    class = 'hover',
    rownames = FALSE
    ) %>% formatStyle(
      'color',
      target = 'cell',
      backgroundColor = styleEqual(
        maintenance_data$atacodecolor$color,
        maintenance_data$atacodecolor$color
      )
    )
    
    # DT::datatable({
    #   maintenance_data$atacodecolor
    # },
    # filter = "top",
    # selection = 'single',
    # class = 'hover',
    # rownames = FALSE
    # ) %>% formatStyle(
    #   'color',
    #   target = 'cell',
    #   backgroundColor = styleEqual(
    #     maintenance_data$atacodecolor$color,
    #     maintenance_data$atacodecolor$color
    #   )
    # )
    
  })
  
  # output$useroptions_maintenance_parameters <- renderUI({
  #   
  #   ns <- session$ns
  # 
  #   parameters <- pool %>%
  #     tbl(in_schema("ecmapp", "parameters")) %>%
  #     filter(
  #       aircraft_type %in% !!input$constructor_actype_pi
  #     ) %>%
  #     collect()
  #   
  #   choices_list <- list()
  #   
  #   choices_opt_list <- list()
  #   
  #   for(table_name in unique(parameters$table_name)){
  #     
  #     choices_list[[table_name]] <- paste0(
  #       parameters$parameter_name[parameters$table_name == table_name],
  #       " (",
  #       parameters$flight_phase[parameters$table_name == table_name],
  #       ")"
  #     )
  #     
  #     choices_opt_list[[table_name]] <- parameters$param_description[parameters$table_name == table_name]
  #     
  #   }
  #   
  #   pickerInput(
  #     ns("constructor_presetname_pi"),
  #     label = "Parameters",
  #     choices = choices_list, 
  #     choicesOpt = list(
  #       subtext = unlist(choices_opt_list)
  #     ),
  #     # selected = "TAKE OFF trends (MAIN)",
  #     options = list(
  #       `live-search`=TRUE
  #     ),
  #     multiple = T
  #   )
  #   
  # })
  
  observeEvent(input$create_atacode,{
    
    showModal(
      modal_create_atacode
    )
    
  })
  
  modal_create_atacode <- modalDialog(
    fluidPage(
      # uiOutput(ns("create_atacode_atacode")),
      textInput(ns("create_atacode_atacode"), "Ata code"),
      # uiOutput(ns("create_atacode_description")),
      textAreaInput(
        ns("create_atacode_description"),
        "Description"
      ),
      colorPickr(
        inputId = ns("cp_create_atacode_color"),
        label = "Pick a color",
        selected = "#28a745",
        # selected = maintenance_data$atacodecolor$color[maintenance_data$atacodecolor$ata_code == input$pi_maintenance_atacode],
        width = '200px'
      ),
      actionBttn(
        ns("ab_create_ata_code"), 
        "Save settings", 
        color = "success"
      )
    ),
    size="l"
  )
  
  observeEvent(input$ab_create_ata_code,{
    
    browser()
    
    if(input$create_atacode_atacode %in% maintenance_data$atacodecolor$ata_code){
      
      showNotification(
        paste0(
          "Ata code ",
          input$create_atacode_atacode,
          " already exists. Please enter another number"
        )
        
      )
      
    }
    
    else{
      # browser()
      
      new_atacodecolor <- data.frame(
        ata_code = input$create_atacode_atacode,
        description = input$create_atacode_description,
        color = input$cp_create_atacode_color,
        operator = input$maintenance_operator_pi
      )
      
      maintenance_data$atacodecolor <- rbind(
        maintenance_data$atacodecolor,
        new_atacodecolor
      )
      
      dbWriteTable(pool, c("ecmapp", "atacodecolor_operator"), value = new_atacodecolor, row.names = FALSE, append = TRUE)
      
    }
    
  })
  
  output$ui_delete_atacode <- renderUI({
    
    if(!is.null(input$useroptions_maintenance_ata_table_rows_selected)){
      
      actionBttn(
        ns("ab_delete_atacode"),
        "Delete ata code",
        color = 'danger'
      )
      
    }
    
  })
  
  observeEvent(input$ab_delete_atacode,{
      
    # browser()
    
    showModal(modal_delete_atacode)
      
  })
  
  
  modal_delete_atacode <- modalDialog(
    fluidPage(
      h3(
        paste0(
          "Do you really want to delete ata code?"
        )
      ),
      # use_waiter(),
      actionBttn(ns("modal_ab_delete_atacode"), "Delete ata code", color = "danger")
    ),
    size="l"
  )
  
  observeEvent(input$modal_ab_delete_atacode,{
    
    browser()
    
    maintenance_data$atacodecolor <- maintenance_data$atacodecolor[
     -input$useroptions_maintenance_ata_table_rows_selected,
      ]
    
    
    dbWriteTable(pool, c("ecmapp", "atacodecolor_operator"), value = maintenance_data$atacodecolor, row.names = FALSE, overwrite = TRUE)
    
    removeModal()
    
    showNotification(
      paste0(
        "Ata code ",
        atacode_to_delete,
        " has been deleted"
      )
    )
    
    # w$hide()
    
  })
  
  output$maintenance_workspace <- renderUI({
      
    fluidRow(
      bs4Card(
        width = 12,
        headerBorder = FALSE,
        collapsible = FALSE,
        fluidRow(
          column(
            8,
            fluidRow(
              column(
                3,
                uiOutput(ns("maintenance_operator"))
              ),
              column(
                3,
                uiOutput(ns("maintenance_actype"))
              ),
              column(
                3,
                uiOutput(ns("maintenance_acreg"))
              )
            )
            
          ),
          br(),
          column(1),
          column(
            3,
            hr(),
            fluidRow(
              actionBttn(ns("update_maintenance_data"), "Update maintenance")
            )
          )
        )
      ),
      
      bs4TabCard(
        width = 12,
        # height = '900px',
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        tabPanel(
          title = "Maintenance table",
          withSpinner(DT::dataTableOutput(ns("maintenance_table"))),
          actionBttn(
            ns("create_maintenance"),
            "Create maintenance",
            color = "success"
          ),
          uiOutput(ns("ui_delete_maintenance"))
        ),
        tabPanel(
          title = "Summary",
          withSpinner(reactableOutput(ns("summary_table")))
        )
        ,tabPanel(
          title = "Maintenance options",
          fluidRow(
            column(
              4,
              uiOutput(ns("useroptions_maintenance_atacode")),
              uiOutput(ns("useroptions_maintenance_color")),
              hr(),
              # uiOutput(ns("useroptions_maintenance_params_all")),
              # uiOutput(ns("useroptions_maintenance_params")),
              actionBttn(
                ns("save_atacodecolor"),
                "Save atacode options",
                color = "success"
              )
            ),
            column(
              8,
              DT::dataTableOutput(ns("useroptions_maintenance_ata_table")),
              # uiOutput(ns("ui_delete_atacode")),
              actionBttn(
                ns("create_atacode"),
                "Create atacode",
                color = "primary"
              )
            )
          )

        )
      )  
    )
    
    
  })
  
}